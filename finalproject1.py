import streamlit as st
import folium
from streamlit_folium import st_folium
from haversine import haversine, Unit
import openrouteservice
from openrouteservice import convert
from datetime import datetime, timedelta
from folium.plugins import BeautifyIcon
import random
import pandas as pd
import altair as alt

# ========== LOGIN SECTION ==========
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

if not st.session_state.is_logged_in:
    st.title("🔐 Driver Tracker Login")

    name = st.text_input("Nama Lengkap")
    department = st.selectbox("Departemen", ["Warehouse", "Shipping", "Production", "Quality Control"])
    kode_kerja = st.text_input("Kode Kerja (Format: TRA-12345)")

    if st.button("Login"):
        if not name.replace(" ", "").isalpha():
            st.error("❌ Nama harus berupa huruf dan tidak boleh kosong.")
        elif not kode_kerja.startswith("TRA-") or not kode_kerja[4:].isdigit() or len(kode_kerja[4:]) != 5:
            st.error("❌ Kode kerja harus dalam format: TRA-12345 (5 angka).")
        else:
            st.session_state.is_logged_in = True
            st.success("✅ Login berhasil! Selamat datang.")
    st.stop()

# ========== MAIN APP ==========

class Driver:
    def __init__(self, name, lat, lon, supplier):
        self.name = name
        self.lat = lat
        self.lon = lon
        self.status = "Waiting"
        self.supplier = supplier
        self.history = []

    def update_position(self, target_lat, target_lon, step=0.001):
        dlat = target_lat - self.lat
        dlon = target_lon - self.lon
        dist = (dlat**2 + dlon**2)**0.5
        if dist >= step:
            self.lat += dlat / dist * step
            self.lon += dlon / dist * step

    def get_position(self):
        return self.lat, self.lon

# Data
HEAD_OFFICE = {"lat": -6.21462, "lon": 106.84513}
DRIVER_START = {
    "Budi": (-6.20000, 106.81667),
    "Fahmi": (-6.23000, 106.80000),
    "Gaga": (-6.22000, 106.84000),
    "Fajar": (-6.25000, 106.86000),
    "Ridwan": (-6.24000, 106.83000)
}

SUPPLIERS = {
    "Budi": "PT Merah Jaya",
    "Fahmi": "CV Biru Abadi",
    "Gaga": "UD Hijau Mandiri",
    "Fajar": "PT Oranye Sejahtera",
    "Ridwan": "CV Hitam Transport"
}

ICON_COLOR = {
    "Budi": "red",
    "Fahmi": "blue",
    "Gaga": "green",
    "Fajar": "orange",
    "Ridwan": "black"
}
ICON_TYPE = {
    "Budi": "truck",
    "Fahmi": "truck",
    "Gaga": "truck",
    "Fajar": "truck",
    "Ridwan": "truck"
}

if "drivers" not in st.session_state:
    st.session_state.drivers = {
        name: Driver(name, lat, lon, SUPPLIERS[name]) for name, (lat, lon) in DRIVER_START.items()
    }
if "ai_chat" not in st.session_state:
    st.session_state.ai_chat = []

# Fungsi Estimasi

def calculate_info(driver):
    pos = driver.get_position()
    office = (HEAD_OFFICE["lat"], HEAD_OFFICE["lon"])
    distance_km = round(haversine(pos, office), 2)
    time_min = int((distance_km / 45) * 60)
    cost = int(distance_km * 6000)
    carbon = round(distance_km * 0.15, 2)
    status = "✅ Sudah sampai" if distance_km < 0.5 else "🚚 Dalam Perjalanan"
    return distance_km, time_min, cost, carbon, status

QUESTION_OPTIONS = {
    "Apakah sudah sampai?": lambda dist: "Sudah" if dist < 0.5 else "Belum Sampai",
    "Apakah terdapat kendala pengiriman?": lambda dist: "Terdapat kemacetan" if dist > 2 else "Ada Kecelakaan",
    "Berapa lama estimasi sampai?": lambda est: f"Sekitar {est} menit lagi",
    "Kenapa belum berangkat?": lambda _: "Masih ada barang yang belum",
    "Jangan Mengantuk": lambda _: "SIAP!"
}

st.set_page_config(page_title="📍 Driver Tracker", layout="wide")
tab = st.tabs(["Live Tracking & Analisis"])[0]

with tab:
    st.sidebar.title("🚦 Info Driver")
    for name, driver in st.session_state.drivers.items():
        st.sidebar.markdown(f"### 👨‍🚜 {name}")
        st.sidebar.write(f"Supplier: **{driver.supplier}**")
        st.sidebar.write(f"Status: {driver.status}")
        toggle = st.sidebar.checkbox(f"Aktifkan Jalan - {name}", value=driver.status == "Jalan")
        driver.status = "Jalan" if toggle else "Waiting"

    client = openrouteservice.Client(key="your_openrouteservice_api_key")
    for driver in st.session_state.drivers.values():
        if driver.status == "Jalan":
            driver.update_position(HEAD_OFFICE["lat"], HEAD_OFFICE["lon"], step=0.001)

    m = folium.Map(location=[HEAD_OFFICE["lat"], HEAD_OFFICE["lon"]], zoom_start=12)
    folium.Marker(
        [HEAD_OFFICE["lat"], HEAD_OFFICE["lon"]],
        popup="🏢 Head Office",
        icon=folium.Icon(color="blue", icon="building")
    ).add_to(m)

    performance_data = []

    for name, driver in st.session_state.drivers.items():
        dist, time_est, cost, carbon, status = calculate_info(driver)
        popup_content = f"""
        👨‍🚜 {name}<br>
        Supplier: {driver.supplier}<br>
        Jarak: {dist} km<br>
        Estimasi: {time_est} min<br>
        Biaya: Rp{cost}<br>
        Emisi: {carbon} kg<br>
        Status: {status}
        """
        if status == "✅ Sudah sampai":
            popup_content += "<br>🎉 Driver sudah sampai!"

        folium.Marker(
            [driver.lat, driver.lon],
            popup=popup_content,
            icon=BeautifyIcon(icon=ICON_TYPE[name], icon_shape='marker', background_color=ICON_COLOR[name], text_color="white")
        ).add_to(m)

        coords = ((driver.lon, driver.lat), (HEAD_OFFICE["lon"], HEAD_OFFICE["lat"]))
        try:
            route = client.directions(coords)
            geometry = route['routes'][0]['geometry']
            decoded = convert.decode_polyline(geometry)
            route_coords = [(coord[1], coord[0]) for coord in decoded['coordinates']]
            folium.PolyLine(locations=route_coords, color="blue", weight=2.5, opacity=0.7).add_to(m)
        except:
            pass

        performance_data.append({"Nama": name, "Jarak (km)": dist, "Estimasi (menit)": time_est, "Emisi (kg)": carbon, "Status": status})

    st.subheader("📍 Live Tracking Driver to Head Office")
    st_data = st_folium(m, width=1000, height=500)

    st.subheader("💬 Chatbot Pengingat Driver")
    selected_driver = st.selectbox("Pilih Driver", list(st.session_state.drivers.keys()))
    selected_question = st.selectbox("Pilih Pertanyaan", list(QUESTION_OPTIONS.keys()))

    if st.button("Kirim Pertanyaan"):
        st.chat_message("user").markdown(f"@{selected_driver}, {selected_question}")
        st.session_state.ai_chat.append({"role": "user", "content": f"@{selected_driver}, {selected_question}"})

        driver = st.session_state.drivers[selected_driver]
        dist, time_est, cost, carbon, status = calculate_info(driver)

        if selected_question == "Apakah sudah sampai?":
            response = QUESTION_OPTIONS[selected_question](dist)
        elif selected_question == "Berapa lama estimasi sampai?":
            response = QUESTION_OPTIONS[selected_question](time_est)
        elif selected_question == "Kenapa belum berangkat?" and driver.status != "Jalan":
            response = QUESTION_OPTIONS[selected_question](None)
        elif selected_question == "Apakah terdapat kendala pengiriman?":
            response = QUESTION_OPTIONS[selected_question](dist)
        elif selected_question == "Jangan Mengantuk":
            response = QUESTION_OPTIONS[selected_question](None)
        else:
            response = "Driver sedang dalam perjalanan."

        st.chat_message("assistant").markdown(f"@{selected_driver}: {response}")
        st.session_state.ai_chat.append({"role": "assistant", "content": f"@{selected_driver}: {response}"})

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    st.subheader("📊 Analisis & Ranking Performa Driver")
    df_perf = pd.DataFrame(performance_data)
    st.dataframe(df_perf.sort_values(by="Estimasi (menit)").reset_index(drop=True))

    st.markdown("#### 📈 Grafik Estimasi Waktu Pengiriman")
    chart = alt.Chart(df_perf).mark_bar().encode(
        x=alt.X('Nama', sort='-y'),
        y='Estimasi (menit)',
        color='Nama'
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)
