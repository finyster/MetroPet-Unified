"""
services/metro_soap_service.py
───────────────────────────────
One‑stop wrapper around every public SOAP endpoint offered by Taipei Metro.
All methods return **native Python structures** (dict / list) so that
higher‑level tools can consume them directly.

Usage
-----
    from services.metro_soap_service import metro_soap_api

    route = metro_soap_api.get_recommended_route("081", "019")
    lost  = metro_soap_api.get_all_lost_items()

Environment
-----------
`METRO_API_USERNAME`, `METRO_API_PASSWORD` should be defined in `.env` or
`config.py`.  Falls back to demo credentials for convenience.

"""
from __future__ import annotations

import json
import os
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re # 新增
import logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
try:
    import config  # type: ignore
    _USER = config.METRO_API_USERNAME
    _PASS = config.METRO_API_PASSWORD
except (ImportError, AttributeError):
    _USER = os.getenv("METRO_API_USERNAME", "MetroTaipeiHackathon2025")
    _PASS = os.getenv("METRO_API_PASSWORD", "bZ0dQG96N")


class MetroSoapApi:
    """Wrapper class for all Taipei‑Metro SOAP services."""

    # ---------------------------------------------------------------------
    # Endpoints mapping
    # ---------------------------------------------------------------------

    _ENDPOINTS = {
        # Route / station list
        "RouteControl": "https://ws.metro.taipei/trtcBeaconBE/RouteControl.asmx",
        # Lost & found
        "LoseThing": "https://api.metro.taipei/metroapi/LoseThingForWeb.asmx",
        # Train arrival list (高運量路線)
        "TrackInfo": "https://api.metro.taipei/metroapi/TrackInfo.asmx",
        # Train info (single train)
        "TrainInfo": "https://mobileapp.metro.taipei/TRTCTraininfo/TrainTimeControl.asmx",
        # Car weight – 板南線 & 高運量 (getCarWeightByInfo / getCarWeightByInfoEx)
        "HighCapacity": "https://api.metro.taipei/metroapi/CarWeight.asmx",
        # Car weight – 文湖線
        "WenhuWeight": "https://api.metro.taipei/metroapi/CarWeightBR.asmx",
        # Parking lot
        "ParkingLot": "https://api.metro.taipei/MetroAPI/ParkingLot.asmx",
        # YouBike near MRT
        "YouBike": "https://api.metro.taipei/MetroAPI/UBike.asmx",
        # Locker
        "Locker": "https://api.metro.taipei/metroapi/locker.asmx",
    }

    # ---------------------------------------------------------------------
    def __init__(self, username: str, password: str) -> None:  # noqa: D401
        self.username = username
        self.password = password

    # ------------------------------------------------------------------
    # Low‑level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _soap_headers(action: str) -> dict[str, str]:
        return {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": action,
        }

    def _request(self, key: str, action: str, body: str, timeout: int = 30) -> requests.Response | None:
        url = self._ENDPOINTS.get(key)
        if not url:
            print(f"❌ Endpoint '{key}' not registered")
            return None
        try:
            r = requests.post(url, data=body.encode("utf-8"), headers=self._soap_headers(action), timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            print(f"❌ SOAP error ({url}): {exc}")
            return None

    # ------------------------------------------------------------------
    # Utility: fetch text of a tag with BeautifulSoup.safe‑getter
    # ------------------------------------------------------------------
    @staticmethod
    def _bs_get(node: BeautifulSoup, tag: str) -> str:
        el = node.find(tag)
        return el.text.strip() if el else ""

    # ------------------------------------------------------------------
    # 1. Recommended route
    # ------------------------------------------------------------------
    def get_recommended_route(self, entry_sid: str, exit_sid: str) -> dict | None:
        # ... (前面的 request 邏輯不變) ...
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body>
<GetRecommandRoute xmlns="http://tempuri.org/">
    <entrySid>{entry_sid}</entrySid>
    <exitSid>{exit_sid}</exitSid>
    <username>{self.username}</username>
    <password>{self.password}</password>
</GetRecommandRoute>
</soap:Body>
</soap:Envelope>"""
        resp = self._request("RouteControl", '"http://tempuri.org/GetRecommandRoute"', body)
        if not resp:
            return None

        text = resp.text.lstrip("\ufeff")
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            print("❌ parse route: cannot locate JSON block")
            return None
        try:
            data = json.loads(match.group())
            logger.debug(f"成功從北捷 SOAP API 解析出 JSON 資料: {data}")
        except json.JSONDecodeError as exc:
            print("❌ parse route JSON error:", exc)
            return None

        path_list = [s for s in data.get("Path", "").split("-") if s and "線" not in s]
        time_value = int(data.get("Time", 0))

        # --- 【✨核心修正✨】重新加入資料合理性檢查 ---
        if len(path_list) > 3 and time_value <= 2:
            logger.warning(f"⚠️ 偵測到官方 API 回傳不合理的時間 ({time_value} 分鐘)，將忽略此結果。")
            return None

        return {
            "path":      path_list,
            "time_min":  time_value,
            "transfers": [s for s in data.get("TransferStations", "").split("-") if s and "線" not in s],
        }

    # ------------------------------------------------------------------
    # 2. Station list
    # ------------------------------------------------------------------

    def get_station_list(self) -> list[dict] | None:
        body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body>
<GetStationList xmlns="http://tempuri.org/" />
</soap:Body>
</soap:Envelope>"""
        resp = self._request("RouteControl", '"http://tempuri.org/GetStationList"', body)
        if not resp:
            return None
        # API 回傳純 JSON 字串（首行）
        json_line = resp.text.splitlines()[0].strip()
        try:
            return json.loads(json_line)
        except json.JSONDecodeError:
            print("⚠️ station list parse failed")
            return None

    # ------------------------------------------------------------------
    # 3. Track info (arrival board)
    # ------------------------------------------------------------------

    def get_track_info(self) -> list[dict] | None:
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body>
<getTrackInfo xmlns="http://tempuri.org/">
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
</getTrackInfo>
</soap:Body>
</soap:Envelope>"""
        resp = self._request("TrackInfo", '"http://tempuri.org/getTrackInfo"', body)
        if not resp:
            return None
        # XML → <getTrackInfoResult>[JSON]</getTrackInfoResult>
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getTrackInfoResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ track info parse failed")
            return None

    # ------------------------------------------------------------------
    # 4. Parking lot
    # ------------------------------------------------------------------

    def _parking_body(self, action: str, station: str | None = None) -> str:
        if action == "getParkingLot":
            return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getParkingLot xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
</getParkingLot>
</soap:Body>
</soap:Envelope>"""
        return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getParkingLotBySationName xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
    <SationName>{station}</SationName>
</getParkingLotBySationName>
</soap:Body>
</soap:Envelope>"""

    def get_parking_lot_all(self) -> list[dict] | None:
        body = self._parking_body("getParkingLot")
        resp = self._request("ParkingLot", '"http://tempuri.org/getParkingLot"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getParkingLotResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ parking lot parse failed")
            return None

    def get_parking_lot_by_station(self, station: str) -> list[dict] | None:
        body = self._parking_body("getParkingLotBySationName", station)
        resp = self._request("ParkingLot", '"http://tempuri.org/getParkingLotBySationName"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getParkingLotBySationNameResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ parking lot (station) parse failed")
            return None

    # ------------------------------------------------------------------
    # 5. YouBike near MRT
    # ------------------------------------------------------------------

    def _youbike_body(self, action: str, station: str | None = None) -> str:
        if action == "getYourBikeNearBy":
            return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getYourBikeNearBy xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
</getYourBikeNearBy>
</soap:Body>
</soap:Envelope>"""
        return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getYourBikeNearByName xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
    <SationName>{station}</SationName>
</getYourBikeNearByName>
</soap:Body>
</soap:Envelope>"""

    def get_youbike_all(self) -> list[dict] | None:
        body = self._youbike_body("getYourBikeNearBy")
        resp = self._request("YouBike", '"http://tempuri.org/getYourBikeNearBy"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getYourBikeNearByResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ YouBike parse failed")
            return None

    def get_youbike_by_station(self, station: str) -> list[dict] | None:
        body = self._youbike_body("getYourBikeNearByName", station)
        resp = self._request("YouBike", '"http://tempuri.org/getYourBikeNearByName"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getYourBikeNearByNameResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ YouBike(station) parse failed")
            return None

    # ------------------------------------------------------------------
    # 6. Locker
    # ------------------------------------------------------------------

    def _locker_body(self, action: str, station: str | None = None) -> str:
        if action == "getLockerMRT":
            return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getLockerMRT xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
</getLockerMRT>
</soap:Body>
</soap:Envelope>"""
        return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getLockerMRTSationName xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
    <SationName>{station}</SationName>
</getLockerMRTSationName>
</soap:Body>
</soap:Envelope>"""

    def get_locker_all(self) -> list[dict] | None:
        body = self._locker_body("getLockerMRT")
        resp = self._request("Locker", '"http://tempuri.org/getLockerMRT"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getLockerMRTResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ locker parse failed")
            return None

    def get_locker_by_station(self, station: str) -> list[dict] | None:
        body = self._locker_body("getLockerMRTSationName", station)
        resp = self._request("Locker", '"http://tempuri.org/getLockerMRTSationName"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getLockerMRTSationNameResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ locker(station) parse failed")
            return None

    # ------------------------------------------------------------------
    # 7. Car weight (crowding) – 板南線 / 高運量
    # ------------------------------------------------------------------

    def get_car_weight_bannan(self) -> list[dict] | None:
        body = f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
<soap:Body>
<getCarWeightByInfo xmlns='http://tempuri.org/'>
    <userName>{self.username}</userName>
    <passWord>{self.password}</passWord>
</getCarWeightByInfo>
</soap:Body>
</soap:Envelope>"""
        resp = self._request("HighCapacity", '"http://tempuri.org/getCarWeightByInfo"', body)
        if not resp:
            return None
        soup = BeautifulSoup(resp.content, "xml")
        txt = self._bs_get(soup, "getCarWeightByInfoResult")
        try:
            return json.loads(txt) if txt else None
        except json.JSONDecodeError:
            print("⚠️ car weight bannan parse failed")
            return None

    # Wenhu & high capacity variants already provided earlier (get_high_capacity_weight / get_wenhu_weight)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
metro_soap_api = MetroSoapApi(username=_USER, password=_PASS)
