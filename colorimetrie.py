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
    required = {"ncs_code", "nom", "noirceur%", "saturation%", "teinte",
                "temperature", "clarte", "luminosite", "is_neutre"}
    missing = required - set(df.columns)
    if missing:
        st.error(f"Colonnes manquantes dans {path} : {', '.join(sorted(missing))}")
        st.stop()
    return df

df = load_data(CSV_PATH)
df["nom"] = df["nom"].fillna("").astype(str)

# =========================
# Sélection avec priorité
# =========================
ADJ_OPTIONS = ["chaud", "froid", "clair", "foncé", "lumineux", "mat", "neutre"]

c1, c2, c3 = st.columns(3)
adj1 = c1.selectbox("Adjectif prioritaire #1", ADJ_OPTIONS, index=0)
adj2 = c2.selectbox("Adjectif prioritaire #2", ADJ_OPTIONS, index=2)
adj3 = c3.selectbox("Adjectif prioritaire #3", ADJ_OPTIONS, index=4)

colA, colB = st.columns(2)
strict_mode = colA.toggle("Mode strict (afficher uniquement les couleurs qui matchent les 3)", value=False)
hide_neutral_unless_chosen = colB.toggle("Masquer les neutres sauf si 'neutre' est choisi", value=False)

# =========================
# Matching des adjectifs
# =========================
def match_adjective(df: pd.DataFrame, adj: str) -> pd.Series:
    if adj == "chaud":
        return df["temperature"].eq("chaud")
    if adj == "froid":
        return df["temperature"].eq("froid")
    if adj == "neutre":
        return df["temperature"].eq("neutre")
    if adj == "clair":
        return df["clarte"].eq("clair")
    if adj == "foncé":
        return df["clarte"].eq("foncé")
    if adj == "lumineux":
        return df["luminosite"].eq("lumineux")
    if adj == "mat":
        return df["luminosite"].eq("mat")
    return pd.Series(False, index=df.index)

m1 = match_adjective(df, adj1)
m2 = match_adjective(df, adj2)
m3 = match_adjective(df, adj3)

df_view = df.copy()

# Option: masquer neutres si non choisis
if hide_neutral_unless_chosen and ("neutre" not in {adj1, adj2, adj3}):
    df_view = df_view[df_view["temperature"] != "neutre"]
    m1 = m1.loc[df_view.index]
    m2 = m2.loc[df_view.index]
    m3 = m3.loc[df_view.index]

# Calcul des RGB/HEX pour l’affichage & PDF
df_view["rgb"] = df_view["ncs_code"].apply(ncs_to_rgb)
df_view["hex"] = df_view["rgb"].apply(rgb_to_hex)

# =========================
# Tri par priorité (scoring)
# =========================
# On convertit les booléens en 0/1 et on trie par (match1, match2, match3, saturation% desc)
df_view["match1"] = m1.astype(int)
df_view["match2"] = m2.astype(int)
df_view["match3"] = m3.astype(int)

if strict_mode:
    result = df_view[(df_view["match1"] == 1) & (df_view["match2"] == 1) & (df_view["match3"] == 1)].copy()
else:
    result = df_view.copy()

# Tri : d’abord priorité 1, puis 2, puis 3, puis saturation décroissante (couleurs plus “présentes” en tête)
result = result.sort_values(
    by=["match1", "match2", "match3", "saturation%"],
    ascending=[False, False, False, False]
).reset_index(drop=True)

# =========================
# Feedback utilisateur
# =========================
tot = len(result)
n1 = int(result["match1"].sum()) if not result.empty else 0
n2 = int((result["match1"] & result["match2"]).sum()) if not result.empty else 0
n3 = int((result["match1"] & result["match2"] & result["match3"]).sum()) if not result.empty else 0

st.write(
    f"**{tot} couleurs** trouvées | "
    f"Match {adj1}: {n1} | "
    f"Match {adj1}+{adj2}: {n2} | "
    f"Match {adj1}+{adj2}+{adj3}: {n3}"
)

if result.empty:
    st.info("Aucune couleur ne correspond (selon le mode choisi). Change l’ordre/priorité, désactive le mode strict, ou autorise les neutres.")
    st.stop()

# =========================
# Aperçu tableau
# =========================
st.dataframe(
    result[["ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte", "match1", "match2", "match3"]],
    use_container_width=True
)

# =========================
# Export CSV (respecte l’ordre priorisé)
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
        "\u00A0": " ",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")

def generate_pdf(dataframe: pd.DataFrame, title: str) -> bytes:
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, _latin1_safe(title), ln=1)

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

        # Textes
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
            if y + swatch_h + 20 > 297 - 15:
                pdf.add_page()
                y = pdf.get_y() + 5

    return pdf.output(dest='S').encode('latin-1', 'replace')

pdf_title = f"Priorité: {adj1} → {adj2} → {adj3}" + ("  |  Mode strict" if strict_mode else "")
pdf_bytes = generate_pdf(result, pdf_title)

st.download_button(
    "Télécharger la sélection en PDF",
    data=pdf_bytes,
    file_name="selection_couleurs.pdf",
    mime="application/pdf"
)

st.caption(
    "Tri par priorité : d’abord les couleurs qui matchent l’adjectif #1, puis #2, puis #3. "
    "Active le mode strict pour imposer les trois à la fois. "
    "Note : conversion NCS→RGB approximative (suffisante pour l’écran)."
)
