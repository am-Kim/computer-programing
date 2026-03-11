import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from pyproj import Transformer
import math
import json
import os

# 1. SETTING HALAMAN
st.set_page_config(page_title="Sistem Survey Lot", layout="wide")

# --- DATA PENGGUNA ---
users_db = {
    "1": {"nama": "Adam", "pass": "admin123"}, 
    "2": {"nama": "Hakim", "pass": "admin123"}, 
    "3": {"nama": "Kiirtnana", "pass": "admin123"}
}

def format_dms(bearing):
    degrees = int(bearing)
    minutes_full = (bearing - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    return f"{degrees}°{minutes:02d}'{seconds:02.0f}\""

def calculate_area(coords):
    n = len(coords)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]
    return abs(area) / 2.0

# 2. SISTEM LOGIN
if 'auth' not in st.session_state:
    st.session_state['auth'] = False

if not st.session_state['auth']:
    st.title("🔐 Log Masuk Sistem Survey Lot")
    with st.form("login"):
        uid = st.text_input("ID Pengguna") 
        pwd = st.text_input("Kata Laluan", type="password")
        if st.form_submit_button("Masuk", use_container_width=True):
            if uid in users_db and pwd == users_db[uid]["pass"]:
                st.session_state['auth'] = True
                st.session_state['username'] = users_db[uid]["nama"]
                st.rerun()
            else:
                st.error("Salah ID/Password")
    st.stop()

# --- 3. SKRIN UTAMA ---
st.sidebar.title(f"👤 {st.session_state['username']}")
st.sidebar.divider()

projections = {
    "EPSG:3168 (GDM2000 RSO)": "epsg:3168", 
    "EPSG:3377 (Cassini Perak)": "epsg:3377", 
    "EPSG:4390 (RSO Kertau)": "epsg:4390", 
    "EPSG:4326 (WGS84)": "epsg:4326"
}
pilihan_proj = st.sidebar.selectbox("Projeksi CSV:", list(projections.keys()))
selected_epsg = projections[pilihan_proj]
zoom_awal = st.sidebar.slider("Zoom Peta Awal", 15, 22, 19)

if st.sidebar.button("🚪 Log Keluar"):
    st.session_state['auth'] = False
    st.rerun()

st.title("🗺️ Sistem Survey Lot")

up = st.file_uploader("Muat naik fail point.csv (E, N)", type=["csv"])

if up:
    try:
        df_raw = pd.read_csv(up)
        df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
        
        if 'N' in df_raw.columns and 'E' in df_raw.columns:
            raw_pts = df_raw[['E', 'N']].values.tolist()
            conv_pts, geojson_coords = [], []
            
            transformer = Transformer.from_crs(selected_epsg, "epsg:4326", always_xy=True) if selected_epsg != "epsg:4326" else None
            
            for e, n in raw_pts:
                if transformer: lon, lat = transformer.transform(e, n)
                else: lon, lat = e, n
                conv_pts.append([lat, lon])
                geojson_coords.append([lon, lat])

            if len(conv_pts) >= 3:
                area_m2 = calculate_area(raw_pts)
                area_acre = area_m2 * 0.000247105
                perimeter = 0
                
                features = []
                table_data = []

                for i in range(len(raw_pts)):
                    p1_r, p2_r = raw_pts[i], raw_pts[(i + 1) % len(raw_pts)]
                    dist = math.sqrt((p2_r[0]-p1_r[0])**2 + (p2_r[1]-p1_r[1])**2)
                    brg = (math.degrees(math.atan2(p2_r[0]-p1_r[0], p2_r[1]-p1_r[1])) + 360) % 360
                    
                    perimeter += dist
                    brg_str = format_dms(brg)
                    dist_str = f"{dist:.3f}"
                    
                    table_data.append({"Dari": i+1, "Ke": (i+1)%len(raw_pts)+1, "Bearing": brg_str, "Jarak (m)": dist_str})
                    
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": [geojson_coords[i], geojson_coords[(i+1)%len(raw_pts)]]},
                        "properties": {"Layer": "Lines", "Bearing": brg_str, "Jarak": f"{dist_str}m"}
                    })

                for i, pt in enumerate(geojson_coords):
                    features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pt}, "properties": {"Layer": "Points", "Stn": f"Stn {i+1}"}})
                
                features.append({
                    "type": "Feature", 
                    "geometry": {"type": "Polygon", "coordinates": [geojson_coords + [geojson_coords[0]]]}, 
                    "properties": {"Layer": "Polygon", "Luas_m2": round(area_m2, 2), "Perimeter_m": round(perimeter, 3), "Ekar": round(area_acre, 4)}
                })

                # --- SIDEBAR INFO & EXPORT (NAMA FAIL BARU) ---
                st.sidebar.divider()
                st.sidebar.success(f"📏 **Luas:** {area_m2:.2f} m²")
                st.sidebar.info(f"🚜 **Ekar:** {area_acre:.4f} Ekar")
                st.sidebar.warning(f"🏃 **Perimeter:** {perimeter:.3f} m")
                
                st.sidebar.download_button(
                    label="📥 Export ke QGIS", 
                    data=json.dumps({"type": "FeatureCollection", "features": features}), 
                    file_name="Survey_Lot.geojson",  # NAMA FAIL TELAH DITUKAR
                    mime="application/json",
                    use_container_width=True
                )

                # --- PETA ---
                avg_lat, avg_lon = sum(p[0] for p in conv_pts)/len(conv_pts), sum(p[1] for p in conv_pts)/len(conv_pts)
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom_awal, max_zoom=22, tiles=None)
                
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
                    attr='Google', name='Paparan Satelit', overlay=True,
                    max_zoom=22, max_native_zoom=18, detect_retina=True
                ).add_to(m)
                
                lot_layer = folium.FeatureGroup(name="Sempadan & Label")
                folium.Polygon(locations=conv_pts, color="cyan", weight=3, fill=True, fill_opacity=0.2).add_to(lot_layer)
                
                for i, p in enumerate(conv_pts):
                    folium.CircleMarker(location=p, radius=5, color="red", fill=True).add_to(lot_layer)
                    
                    p1_v, p2_v = conv_pts[i], conv_pts[(i + 1) % len(conv_pts)]
                    mid = [(p1_v[0]+p2_v[0])/2, (p1_v[1]+p2_v[1])/2]
                    label_text = f"{table_data[i]['Bearing']} | {table_data[i]['Jarak (m)']}m"
                    folium.Marker(location=mid, icon=folium.DivIcon(html=f'<div style="font-size: 8pt; color: yellow; font-weight: bold; text-shadow: 1px 1px 2px black; white-space: nowrap;">{label_text}</div>')).add_to(lot_layer)

                lot_layer.add_to(m)
                folium.LayerControl(position='topright', collapsed=False).add_to(m)
                folium_static(m, width=1300, height=600)

                st.subheader("📋 Ringkasan Data Ukur")
                st.table(pd.DataFrame(table_data))

            else: st.warning("Perlu minimum 3 titik.")
    except Exception as e: st.error(f"Ralat: {e}")