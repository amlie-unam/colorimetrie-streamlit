# -*- coding: utf-8 -*-
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from fpdf import FPDF

# =========================
# App config
# =========================
st.set_page_config(page_title="Nuancier NCS", layout="wide")

CSV_PATH = "palette_ncs_avec_adjectifs.csv"  # doit être à côté de ce fichier

# =========================
# Utils NCS -> RGB (approx)
# =========================
BASE = {
    "R": (1.0, 0.0, 0.0),
    "Y": (1.0, 1.0, 0.0),
    "G": (0.0, 1.0, 0.0),
    "B": (0.0, 0.0, 1.0),
    "W": (1.0, 1.0, 1.0),
    "S": (0.0, 0.0, 0.0),  # Svart/Black
}

def _mix(c1, c2, t):
    return tuple((1 - t) * a + t * b for a, b in zip(c1, c2))

def hue_to_rgb(hue: str):
    if not hue or hue.upper() == "N":
        return BASE["W"]
    hue = hue.strip().upper()
    if hue in BASE:
        return BASE[hue]
    m = re.match(r"^([RGBY])(\d{1,2})([RGBY])$", hue)
    if m:
        a, pct, b = m.group(1), int(m.group(2)), m.group(3)
        t = pct / 100.0
        return _mix(BASE[a], BASE[b], t)
    # Fallback: moyenne des lettres présentes
    letters = [ch for ch in hue if ch in BASE]
    if not letters:
        return BASE["W"]
    r = sum(BASE[ch][0] for ch in letters) / len(letters)
    g = sum(BASE[ch][1] for ch in letters) / len(letters)
    b = sum(BASE[ch][2] for ch in letters) / len(letters)
    return (r, g, b)

def ncs_to_rgb(ncs_code: str):
    """
    Attend 'SBBCC-HUE' (ex: S0502-Y, S3560-Y30R, S0300-N)
    Retourne un tuple (R,G,B) en 0..255
    """
    m = re.match(r"^S\s*(\d{2})(\d{2})\s*-\s*([A-Z](?:\d{1,2}[A-Z])?|N)$", (ncs_code or "").replace(" ", ""))
    if not m:
        return (200, 200, 200)
    blackness = int(m.group(1))
    chroma    = int(m.group(2))
    hue       = m.group(3)
    whiteness = max(0, 100 - blackness - chroma)

    hr, hg, hb = hue_to_rgb(hue)
    r = (chroma/100.0)*hr + (whiteness/100.0)*BASE["W"][0] + (blackness/100.0)*BASE["S"][0]
    g = (chroma/100.0)*hg + (whiteness/100.0)*BASE["W"][1] + (blackness/100.0)*BASE["S"][1]
    b = (chroma/100.0)*hb + (whiteness/100.0)*BASE["W"][2] + (blackness/100.0)*BASE["S"][2]
    return (int(round(r*255)), int(round(g*255)), int(round(b*255)))

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)

# =========================
# Chargement des données
# =========================
@st.cache_data
def load_data(path: str):
    df = pd.read_csv(path, sep=";")
    # Colonnes minimales attendues
    required = {"ncs_code", "nom", "noirceur%", "saturation%", "teinte",
                "temperature", "clarte", "luminosite", "is_neutre"}
    missing = required - set(df.columns)
    if missing:
        st.error(f"Colonnes manquantes dans {path} : {', '.join(sorted(missing))}")
        st.stop()
    return df

df = load_data(CSV_PATH)

# =========================
# UI filtres (2 options)
# =========================
col1, col2, col3 = st.columns(3)
temperature = col1.selectbox("Température", ["chaud", "froid"], index=0)
clarte      = col2.selectbox("Clarté", ["clair", "foncé"], index=0)
luminosite  = col3.selectbox("Luminance", ["lumineux", "mat"], index=0)
inclure_neutres = st.toggle("Inclure aussi les neutres (autour de S3030)", value=False)

# =========================
# Filtrage
# =========================
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

if result.empty:
    st.info("Aucune couleur ne correspond à ces 3 adjectifs. Essaie une autre combinaison ou active l’option 'Inclure aussi les neutres'.")
    st.stop()

# =========================
# Couleurs HEX pour rendu
# =========================
# (évite les NaN pour 'nom' qui cassent FPDF plus loin)
result["nom"] = result["nom"].fillna("").astype(str)

# Ajout des RGB/HEX si pas déjà présent
if "hex" not in result.columns or "rgb" not in result.columns:
    result["rgb"] = result["ncs_code"].apply(ncs_to_rgb)
    result["hex"] = result["rgb"].apply(rgb_to_hex)
else:
    # si 'rgb' est stocké en str, on pourrait reparser, mais ici on recalcule pour fiabilité
    result["rgb"] = result["ncs_code"].apply(ncs_to_rgb)
    result["hex"] = result["rgb"].apply(rgb_to_hex)

# =========================
# Aperçu tableau
# =========================
st.dataframe(
    result[["ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte"]],
    use_container_width=True
)

# =========================
# Export CSV
# =========================
st.download_button(
    "Exporter la sélection (CSV)",
    data=result[["ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte"]]
         .to_csv(index=False, sep=";").encode("utf-8"),
    file_name="selection_couleurs.csv",
    mime="text/csv"
)

# =========================
# PDF (via FPDF, pas reportlab)
# =========================
def _latin1_safe(s: str) -> str:
    """Convertit les caractères non-latin1 pour éviter les erreurs FPDF."""
    if s is None:
        return ""
    repl = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "•": "-",
        "…": "...",
        "\u00A0": " ",  # espace insécable
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")

def generate_pdf(dataframe: pd.DataFrame, temperature: str, clarte: str, luminosite: str) -> bytes:
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    titre = f"Sélection ({temperature}, {clarte}, {luminosite})"
    pdf.cell(0, 8, _latin1_safe(titre), ln=1)

    left_margin, right_margin = 15, 15
    usable_width = 210 - left_margin - right_margin
    cols, swatch_h, gap_y = 3, 25, 10
    swatch_w = usable_width / cols
    col, x0, y = 0, left_margin, pdf.get_y() + 5

    for _, row in dataframe.iterrows():
        x = x0 + col * swatch_w

        # Pastille couleur
        r, g, b = row["rgb"]
        pdf.set_fill_color(int(r), int(g), int(b))
        pdf.rect(x, y, swatch_w, swatch_h, style='F')

        # Textes (assainis latin-1)
        pdf.set_xy(x, y + swatch_h + 3)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=9)

        label1 = f"{row['ncs_code']}  |  {row['nom']}"
        label2 = (
            f"Noirceur: {row['noirceur%']}  |  "
            f"Saturation: {row['saturation%']}  |  "
            f"Teinte: {row['teinte']}  |  {row['hex']}"
        )
        pdf.multi_cell(w=swatch_w, h=5, txt=_latin1_safe(label1), border=0, align='L')
        pdf.set_x(x)
        pdf.multi_cell(w=swatch_w, h=5, txt=_latin1_safe(label2), border=0, align='L')

        col += 1
        if col >= cols:
            col = 0
            y = pdf.get_y() + gap_y
            # pagination
            if y + swatch_h + 20 > 297 - 15:  # bas de page (A4=297mm)
                pdf.add_page()
                y = pdf.get_y() + 5

    # IMPORTANT: récupérer les bytes via dest='S' et encoder latin-1
    return pdf.output(dest='S').encode('latin-1', 'replace')

pdf_bytes = generate_pdf(result, temperature, clarte, luminosite)

st.download_button(
    "Télécharger la sélection en PDF",
    data=pdf_bytes,
    file_name="selection_couleurs.pdf",
    mime="application/pdf"
)

st.caption("Note : conversion NCS→RGB approximative (suffisante pour l’écran).")
