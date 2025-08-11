import pandas as pd
import streamlit as st
import re
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.colors import Color
from io import BytesIO

st.set_page_config(page_title="Nuancier NCS", layout="wide")

# -----------------------------
# Chargement du CSV maître
# -----------------------------
@st.cache_data
def load_data():
    return pd.read_csv("palette_ncs_avec_adjectifs.csv", sep=";")
df = load_data()

# -----------------------------
# Menus 2-options (adjectifs)
# -----------------------------
col1, col2, col3 = st.columns(3)
temperature = col1.selectbox("Température", ["chaud", "froid"], index=0)
clarte      = col2.selectbox("Clarté", ["clair", "foncé"], index=0)
luminosite  = col3.selectbox("Luminance", ["lumineux", "mat"], index=0)
inclure_neutres = st.toggle("Inclure aussi les neutres (autour de S3030)", value=False)

# -----------------------------
# Filtrage
# -----------------------------
mask = (
    (df["temperature"] == temperature) &
    (df["clarte"] == clarte) &
    (df["luminosite"] == luminosite)
)
if inclure_neutres:
    mask = mask | (
        (df["temperature"] == "neutre") &
        (df["clarte"] == clarte) &
        (df["luminosite"] == luminosite)
    )

result = df[mask].copy()
st.write(f"**{len(result)} couleurs** trouvées")
st.dataframe(result[["ncs_code","nom","noirceur%","saturation%","teinte"]], use_container_width=True)

# -----------------------------
# Conversion NCS -> RGB/HEX (approx)
# -----------------------------
BASE = {
    "R": (1.0, 0.0, 0.0),
    "Y": (1.0, 1.0, 0.0),
    "G": (0.0, 1.0, 0.0),
    "B": (0.0, 0.0, 1.0),
    "W": (1.0, 1.0, 1.0),
    "S": (0.0, 0.0, 0.0),  # Svart/Black
}

def mix(c1, c2, t):
    return tuple((1-t)*a + t*b for a, b in zip(c1, c2))

def hue_to_rgb(hue: str):
    if hue is None or hue.upper() == "N":
        return BASE["W"]
    hue = hue.strip().upper()
    if hue in BASE:
        return BASE[hue]
    m = re.match(r"^([RGBY])(\d{1,2})([RGBY])$", hue)
    if m:
        a, pct, b = m.group(1), int(m.group(2)), m.group(3)
        t = pct / 100.0
        return mix(BASE[a], BASE[b], t)
    letters = [ch for ch in hue if ch in BASE]
    if not letters:
        return BASE["W"]
    r = sum(BASE[ch][0] for ch in letters) / len(letters)
    g = sum(BASE[ch][1] for ch in letters) / len(letters)
    b = sum(BASE[ch][2] for ch in letters) / len(letters)
    return (r, g, b)

def ncs_to_rgb(ncs_code: str):
    m = re.match(r"^S\s*(\d{2})(\d{2})\s*-\s*([A-Z](?:\d{1,2}[A-Z])?|N)$", ncs_code.replace(" ", ""))
    if not m:
        return (200, 200, 200)
    b = int(m.group(1))   # blackness
    c = int(m.group(2))   # chroma
    hue = m.group(3)
    w = max(0, 100 - b - c)  # whiteness

    hue_rgb = hue_to_rgb(hue)
    r = (c/100.0)*hue_rgb[0] + (w/100.0)*BASE["W"][0] + (b/100.0)*BASE["S"][0]
    g = (c/100.0)*hue_rgb[1] + (w/100.0)*BASE["W"][1] + (b/100.0)*BASE["S"][1]
    b_ = (c/100.0)*hue_rgb[2] + (w/100.0)*BASE["W"][2] + (b/100.0)*BASE["S"][2]
    return (int(round(r*255)), int(round(g*255)), int(round(b_*255)))

def rgb_to_hex(rgb): 
    return "#{:02X}{:02X}{:02X}".format(*rgb)

# Ajout des couleurs calculées
result["rgb"] = result["ncs_code"].apply(ncs_to_rgb)
result["hex"] = result["rgb"].apply(rgb_to_hex)

# -----------------------------
# Export CSV
# -----------------------------
st.download_button(
    "Exporter la sélection (CSV)",
    data=result[["ncs_code","nom","hex","noirceur%","saturation%","teinte"]].to_csv(index=False, sep=";").encode("utf-8"),
    file_name="selection_couleurs.csv",
    mime="text/csv"
)

# -----------------------------
# Génération du PDF
# -----------------------------
def generate_pdf(dataframe: pd.DataFrame) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    margin = 1.5*cm
    swatch_w = (width - 2*margin) / 3.0
    swatch_h = 2.2*cm
    x0 = margin
    y = height - margin - swatch_h

    c.setFont("Helvetica-Bold", 12)
    titre = f"Sélection ({temperature}, {clarte}, {luminosite})"
    c.drawString(margin, height - margin + 0.2*cm, titre)

    col = 0

    for _, row in dataframe.iterrows():
        x = margin + col*swatch_w

        r, g, b = row["rgb"]
        c.setFillColor(Color(r/255.0, g/255.0, b/255.0))
        c.rect(x, y, swatch_w, swatch_h, fill=1, stroke=0)

        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 9)
        text_y = y - 0.15*cm
        c.drawString(x, text_y, f"{row['ncs_code']}  |  {row['nom']}")
        c.drawString(x, text_y - 0.4*cm, f"Noirceur: {row['noirceur%']}  |  Saturation: {row['saturation%']}  |  Teinte: {row['teinte']}  |  {row['hex']}")

        col += 1
        if col >= 3:
            col = 0
            y -= (swatch_h + 1.2*cm)
            if y < margin + swatch_h:
                c.showPage()
                y = height - margin - swatch_h
                c.setFont("Helvetica-Bold", 12)
                c.drawString(margin, height - margin + 0.2*cm, "Sélection — suite")

    c.save()
    buf.seek(0)
    return buf.getvalue()

pdf_bytes = generate_pdf(result)

st.download_button(
    "Télécharger la sélection en PDF",
    data=pdf_bytes,
    file_name="selection_couleurs.pdf",
    mime="application/pdf"
)

st.caption("Couleurs dans le PDF : conversion NCS→RGB approximative pour rendu écran.")
