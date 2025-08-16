# -*- coding: utf-8 -*-
import re
import colorsys
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
# Sélection avec priorité (adjectifs)
# =========================
# Tu peux garder toutes les options, mais par défaut on propose chaud/clair/lumineux
ADJ_OPTIONS = ["chaud", "froid", "clair", "foncé", "lumineux", "mat", "neutre"]

c1, c2, c3 = st.columns(3)
adj1 = c1.selectbox("Adjectif prioritaire #1", ADJ_OPTIONS, index=0)  # chaud
adj2 = c2.selectbox("Adjectif prioritaire #2", ADJ_OPTIONS, index=2)  # clair
adj3 = c3.selectbox("Adjectif prioritaire #3", ADJ_OPTIONS, index=4)  # lumineux

# On garde seulement ce toggle (utile en pratique)
colA, _ = st.columns(2)
hide_neutral_unless_chosen = colA.toggle("Masquer les neutres sauf si 'neutre' est choisi", value=False)

# =========================
# Préparation des données
# =========================
df_view = df.copy()

# Option: masquer neutres si non choisis
if hide_neutral_unless_chosen and ("neutre" not in {adj1, adj2, adj3}):
    df_view = df_view[df_view["temperature"] != "neutre"]

# Calcul des RGB/HEX pour l’affichage & PDF
df_view["rgb"] = df_view["ncs_code"].apply(ncs_to_rgb)
df_view["hex"] = df_view["rgb"].apply(rgb_to_hex)

# =========================
# Matching flou (scoring 0..1)
# =========================
def score_adjective(row: pd.Series, adj: str) -> float:
    """
    Retourne un score 0..1 pour l'adjectif demandé, en combinant les colonnes disponibles.
    Logique:
      - chaud/froid/neutre : s'appuie sur 'temperature' avec tolérance
      - clair/foncé        : s'appuie sur 'noirceur%' (blackness) + étiquette 'clarte'
      - lumineux/mat       : s'appuie d'abord sur 'luminosite' (catégoriel), sinon la saturation%
    """
    temp = (row.get("temperature") or "").strip().lower()
    clar = (row.get("clarte") or "").strip().lower()
    lumo = (row.get("luminosite") or "").strip().lower()
    noir = float(row.get("noirceur%", 0))      # 0..100
    sat  = float(row.get("saturation%", 0))    # 0..100

    if adj == "chaud":
        return 1.0 if temp == "chaud" else (0.6 if temp == "neutre" else 0.0)

    if adj == "froid":
        return 1.0 if temp == "froid" else (0.6 if temp == "neutre" else 0.0)

    if adj == "neutre":
        if temp == "neutre":
            base = 1.0
        else:
            base = 0.0
        bonus = max(0.0, (10.0 - sat) / 10.0)  # sat<=10 → bonus jusqu’à +1
        return min(1.0, base + 0.6 * bonus)

    if adj == "clair":
        s = 1.0 - (noir / 100.0)
        if clar == "clair":
            s = min(1.0, s + 0.15)
        return s

    if adj == "foncé":
        s = noir / 100.0
        if clar == "foncé":
            s = min(1.0, s + 0.15)
        return s

    if adj == "lumineux":
        if lumo == "lumineux":
            return 1.0
        return 0.3 + 0.7 * (sat / 100.0)

    if adj == "mat":
        if lumo == "mat":
            return 1.0
        return 0.7 * (1.0 - sat / 100.0)

    return 0.0

def color_family_from_rgb(rgb_tuple):
    """
    Classe une couleur en famille basique via HSV.hue:
      red, orange, yellow, green, cyan, blue, violet, magenta, grey
    Utilisé pour diversifier automatiquement le top (équilibrage actif en dur).
    """
    r, g, b = [c / 255.0 for c in rgb_tuple]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)  # h in [0,1)
    if s < 0.05 or v < 0.1:
        return "grey"
    deg = h * 360.0
    if   345 <= deg or deg < 15:   return "red"
    if   15 <= deg < 45:           return "orange"
    if   45 <= deg < 75:           return "yellow"
    if   75 <= deg < 165:          return "green"
    if  165 <= deg < 195:          return "cyan"
    if  195 <= deg < 255:          return "blue"
    if  255 <= deg < 300:          return "violet"
    if  300 <= deg < 345:          return "magenta"
    return "other"

# Scores par adjectif (pondérés plus tard)
df_view["s1"] = df_view.apply(lambda r: score_adjective(r, adj1), axis=1)
df_view["s2"] = df_view.apply(lambda r: score_adjective(r, adj2), axis=1)
df_view["s3"] = df_view.apply(lambda r: score_adjective(r, adj3), axis=1)

# =========================
# Tri par priorité (strict ON, seuil fixe, équilibrage ON)
# =========================
# Pondérations par priorité (1>2>3)
w1, w2, w3 = 1.0, 0.6, 0.3

# Mode strict ON + seuil fixe
SEUIL_STRICT = 0.60
mask_strict = (df_view["s1"] >= SEUIL_STRICT) & (df_view["s2"] >= SEUIL_STRICT) & (df_view["s3"] >= SEUIL_STRICT)
result = df_view.loc[mask_strict].copy()

# Score global (bonus léger à la saturation)
result["score_global"] = (w1 * result["s1"] + w2 * result["s2"] + w3 * result["s3"]) + 0.05 * (result["saturation%"] / 100.0)

# Famille de teinte + tri
result["famille"] = result["rgb"].apply(color_family_from_rgb)
result = result.sort_values(by="score_global", ascending=False).reset_index(drop=True)

# Équilibrage ON (round-robin par familles sur le top N)
if not result.empty:
    topN = 200
    top = result.head(topN).copy()
    groups = {fam: df_fam.reset_index(drop=True) for fam, df_fam in top.groupby("famille")}
    order = []
    fams = list(groups.keys())
    i = 0
    while any(len(g) > 0 for g in groups.values()):
        fam = fams[i % len(fams)]
        if len(groups[fam]) > 0:
            order.append(groups[fam].iloc[0])
            groups[fam] = groups[fam].iloc[1:]
        i += 1
    diversified = pd.DataFrame(order)
    result = pd.concat([diversified, result.iloc[topN:]], ignore_index=True)

# =========================
# Feedback utilisateur
# =========================
tot = len(result)
st.write(f"**{tot} couleurs** trouvées | Mode strict: **ON** | Seuil: **{SEUIL_STRICT:.2f}** | Équilibrage familles: **ON**")

if result.empty:
    st.info("Aucune couleur ne dépasse le seuil fixé pour les trois adjectifs. Modifie l’ordre/priorité ou choisis d’autres adjectifs.")
    st.stop()

# =========================
# Aperçu tableau
# =========================
st.dataframe(
    result[[
        "ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte",
        "temperature", "clarte", "luminosite", "famille",
        "s1", "s2", "s3", "score_global"
    ]],
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
# PDF (via FPDF)
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

pdf_title = f"Priorité: {adj1} → {adj2} → {adj3}  |  Strict: ON  |  Seuil: {SEUIL_STRICT:.2f}  |  Équilibrage: ON"
pdf_bytes = generate_pdf(result, pdf_title)

st.download_button(
    "Télécharger la sélection en PDF",
    data=pdf_bytes,
    file_name="selection_couleurs.pdf",
    mime="application/pdf"
)

st.caption(
    "Matching flou avec scoring (0..1), priorité pondérée (1>2>3), mode strict ON (seuil 0.65) et équilibrage des familles de teinte ON. "
    "Note : conversion NCS→RGB approximative (suffisante pour l’écran)."
)

