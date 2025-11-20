# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import re
import colorsys
import base64
import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import requests
from fpdf import FPDF

# =========================
# App config
# =========================
st.set_page_config(page_title="Nuancier NCS",
                   layout="wide",
                   initial_sidebar_state="expanded")

# =========================
# Logo config (local + GitHub)
# =========================
LOGO_PATH = Path(__file__).parent / "logo_coloriste.png"
LOGO_URL = st.secrets.get("LOGO_URL", "").strip()

# ---- Taille du logo (modifiable) ----
LOGO_MAX_PX = 48  # <== change cette valeur pour agrandir/rétrécir le logo

_pdf_logo_path = None
_html_logo_src = None

def _load_logo_sources():
    global _pdf_logo_path, _html_logo_src
    if LOGO_PATH.exists():
        try:
            b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
            _html_logo_src = f"data:image/png;base64,{b64}"
            _pdf_logo_path = str(LOGO_PATH)
            return
        except Exception:
            pass
    if LOGO_URL:
        try:
            resp = requests.get(LOGO_URL, timeout=10)
            resp.raise_for_status()
            _html_logo_src = LOGO_URL
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(resp.content); tmp.flush()
            _pdf_logo_path = tmp.name
            return
        except Exception:
            pass

_load_logo_sources()

# =========================
# UI THEME (neutre, chic)
# =========================
THEME = {
    "bg": "#FEFEFE",
    "panel": "#F4F1EC",
    "text": "#3E2F2A",
    "muted": "#6B5E56",
    "accent": "#C8A165",
    "accent_hover": "#A48B78",
    "shadow": "rgba(0,0,0,0.06)"
}

# =========================
# CSS
# =========================
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&family=Playfair+Display:wght@600;700&display=swap');

:root {{
  --logo-max-height: {LOGO_MAX_PX}px; /* <- tu peux aussi modifier la taille ici */
}}

html, body, [data-testid="stAppViewContainer"] {{
  background: {THEME['bg']} !important;
  color: {THEME['text']};
  font-family: 'Nunito', sans-serif;
}}
.block-container {{ padding-top: 1rem; }}

h1,h2,h3,.stMarkdown h1,.stMarkdown h2,.stMarkdown h3 {{
  font-family: 'Playfair Display', serif;
  color: {THEME['text']};
}}

/* On rend la sidebar "relative" pour pouvoir ancrer un enfant en bas à gauche */
div[data-testid="stSidebar"] {{
  background: {THEME['panel']};
  border-right: 1px solid rgba(0,0,0,0.05);
  position: relative;
}}

.stSelectbox [data-baseweb="select"] > div {{
  border-radius:14px; 
  background: white;
  box-shadow: 0 2px 6px {THEME['shadow']};
}}
.stSelectbox label {{ color: {THEME['muted']}; font-weight:600; }}

.stButton>button {{
  background: {THEME['accent']};
  color: white; font-weight:700;
  border: 0; border-radius:14px; padding:10px 16px;
  box-shadow: 0 6px 18px {THEME['shadow']};
}}
.stButton>button:hover {{ background: {THEME['accent_hover']}; }}

.card {{
  background: {THEME['panel']}; 
  border-radius:18px; 
  padding:12px;
  border: 1px solid rgba(0,0,0,0.05);
  box-shadow: 0 8px 22px {THEME['shadow']};
}}
.swatch {{ height: 72px; border-radius:14px; margin-bottom:10px; }}

.app-title {{ text-align:center !important; }}

.card {{ padding:8px !important; border-radius:14px !important; }}
.swatch {{ height: 72px !important; }}

/* ---- LOGOS ---- */

/* Logo INSIDE sidebar (visible quand la sidebar est ouverte) */
.sidebar-logo-wrapper {{
  position: absolute;  /* ancré au container de la sidebar */
  left: 14px;
  bottom: 14px;
  z-index: 10;
  pointer-events: none;   /* ne bloque pas les clics */
}}
.sidebar-logo-wrapper img {{
  max-height: var(--logo-max-height);
  filter: drop-shadow(0 2px 6px {THEME['shadow']});
}}

/* Logo FIXE dans le viewport (visible quand la sidebar est cachée) */
.page-logo-fixed {{
  position: fixed;
  left: 14px;
  bottom: 14px;
  z-index: 1000;
  opacity: .98;
  pointer-events: none;
  display: none;          /* masqué par défaut, JS le montrera si sidebar cachée */
}}
.page-logo-fixed img {{
  max-height: var(--logo-max-height);
  filter: drop-shadow(0 2px 6px {THEME['shadow']});
}}
</style>
""", unsafe_allow_html=True)

# =========================
# Insertion des logos (un dans la sidebar, un fixe en fallback)
# =========================
if _html_logo_src:
    with st.sidebar:
        st.markdown(f'<div class="sidebar-logo-wrapper"><img src="{_html_logo_src}" alt="logo"/></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-logo-fixed" id="fallback-logo"><img src="{_html_logo_src}" alt="logo"/></div>', unsafe_allow_html=True)
else:
    st.info("ℹ️ Ajoute `logo_coloriste.png` au repo ou définis `LOGO_URL` dans les *Secrets* pour afficher le logo.")

# =========================
# JS (optionnel: masquer flèches + toggle des logos selon visibilité sidebar)
# =========================
components.html("""
<!DOCTYPE html><html><body><script>
(function(){
  /* Masquer les flèches (peut être supprimé si tu veux les garder) */
  function hideCollapseButtons(root){
    const sels=[
      '[data-testid="collapsedControl"]',
      'button[title*="Collapse"]',
      'button[aria-label*="Collapse"]',
      'button[aria-label*="Réduire"]',
      'button[aria-label*="Replier"]',
      '[data-testid="baseButton-headerNoPadding"]'
    ];
    for(const s of sels){
      const el=(root||document).querySelector(s);
      if(el){
        Object.assign(el.style,{
          display:'none',visibility:'hidden',opacity:'0',
          pointerEvents:'none',width:'0px',height:'0px',margin:'0',padding:'0'
        });
      }
    }
  }

  /* Montre le logo fixe si la sidebar est cachée; sinon montre le logo dans la sidebar */
  function toggleLogos(){
    try{
      const pd = (window.parent && window.parent.document) || document;
      const sb = pd.querySelector('[data-testid="stSidebar"]');
      const fb = document.getElementById('fallback-logo'); // logo fixe dans l'app
      const visible = sb && (sb.offsetWidth > 0) && getComputedStyle(sb).display !== 'none';
      if(fb){ fb.style.display = visible ? 'none' : 'block'; }
    }catch(e){}
  }

  // Initial
  hideCollapseButtons(document);
  try{ hideCollapseButtons(window.parent && window.parent.document); }catch(e){}
  toggleLogos();

  const opts = {childList:true, subtree:true, attributes:true};
  new MutationObserver(()=>{ hideCollapseButtons(document); toggleLogos(); })
      .observe(document.documentElement, opts);

  try{
    const pd = window.parent && window.parent.document;
    if(pd){
      new MutationObserver(()=>{ hideCollapseButtons(pd); toggleLogos(); })
          .observe(pd.documentElement, opts);
      const sb = pd.querySelector('[data-testid="stSidebar"]');
      if(sb){ new ResizeObserver(toggleLogos).observe(sb); }
      pd.defaultView && pd.defaultView.addEventListener('resize', toggleLogos);
    }
  }catch(e){}
  window.addEventListener('resize', toggleLogos);
})();
</script></body></html>
""", height=0, scrolling=False)

# =========================
# HEADER
# =========================
st.markdown(
    f"""
    <div class="app-title" style="line-height:1.1">
      <div style="font-family:'Abril Fatface', serif;
                  font-size:36px; font-weight:700; color:{THEME['text']}">
          Nuancier personnalisé
      </div>
      <div style="color:{THEME['muted']}; margin-top:4px">
          Outil adapté à toutes les palettes
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

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

def _mix(c1, c2, t): return tuple((1 - t) * a + t * b for a, b in zip(c1, c2))

def hue_to_rgb(hue: str):
    if not hue or hue.upper() == "N": return BASE["W"]
    hue = hue.strip().upper()
    if hue in BASE: return BASE[hue]
    m = re.match(r"^([RGBY])(\d{1,2})([RGBY])$", hue)
    if m:
        a, pct, b = m.group(1), int(m.group(2)), m.group(3)
        t = pct / 100.0
        return _mix(BASE[a], BASE[b], t)
    letters = [ch for ch in hue if ch in BASE]
    if not letters: return BASE["W"]
    r = sum(BASE[ch][0] for ch in letters) / len(letters)
    g = sum(BASE[ch][1] for ch in letters) / len(letters)
    b = sum(BASE[ch][2] for ch in letters) / len(letters)
    return (r, g, b)

def ncs_to_rgb(ncs_code: str):
    m = re.match(r"^S\s*(\d{2})(\d{2})\s*-\s*([A-Z](?:\d{1,2}[A-Z])?|N)$", (ncs_code or "").replace(" ", ""))
    if not m: return (200, 200, 200)
    blackness = int(m.group(1)); chroma = int(m.group(2)); hue = m.group(3)
    whiteness = max(0, 100 - blackness - chroma)
    hr, hg, hb = hue_to_rgb(hue)
    r = (chroma/100.0)*hr + (whiteness/100.0)*BASE["W"][0] + (blackness/100.0)*BASE["S"][0]
    g = (chroma/100.0)*hg + (whiteness/100.0)*BASE["W"][1] + (blackness/100.0)*BASE["S"][1]
    b = (chroma/100.0)*hb + (whiteness/100.0)*BASE["W"][2] + (blackness/100.0)*BASE["S"][2]
    return (int(round(r*255)), int(round(g*255)), int(round(b*255)))

def rgb_to_hex(rgb): return "#{:02X}{:02X}{:02X}".format(*rgb)

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
# Filtres (sidebar)
# =========================
with st.sidebar:
    st.markdown("### Vos critères")
    ADJ_OPTIONS = ["Chaud", "Froid", "Clair", "Foncé", "Lumineux", "Mat", "Neutre"]
    adj1 = st.selectbox("Adjectif prioritaire #1", ADJ_OPTIONS, index=ADJ_OPTIONS.index("Chaud"))
    adj2 = st.selectbox("Adjectif prioritaire #2", ADJ_OPTIONS, index=ADJ_OPTIONS.index("Clair"))
    adj3 = st.selectbox("Adjectif prioritaire #3", ADJ_OPTIONS, index=ADJ_OPTIONS.index("Lumineux"))
    with st.expander("Options avancées"):
        SEUIL_STRICT = st.slider("Exigence du matching", 0.0, 1.0, 0.60, 0.05, key="seuil_strict")
        

if "SEUIL_STRICT" not in locals(): SEUIL_STRICT = 0.60


# =========================
# Préparation des données
# =========================
df_view = df.copy()
df_view["rgb"] = df_view["ncs_code"].apply(ncs_to_rgb)
df_view["hex"] = df_view["rgb"].apply(rgb_to_hex)

def score_adjective(row: pd.Series, adj: str) -> float:
    adj = (adj or "").strip().lower()
    temp = (row.get("temperature") or "").strip().lower()
    clar = (row.get("clarte") or "").strip().lower()
    lumo = (row.get("luminosite") or "").strip().lower()
    noir = float(row.get("noirceur%", 0)); sat  = float(row.get("saturation%", 0))
    if adj == "chaud":  return 1.0 if temp == "chaud" else (0.6 if temp == "neutre" else 0.0)
    if adj == "froid":  return 1.0 if temp == "froid" else (0.6 if temp == "neutre" else 0.0)
    if adj == "neutre":
        base = 1.0 if temp == "neutre" else 0.0
        bonus = max(0.0, (10.0 - sat) / 10.0)
        return min(1.0, base + 0.6 * bonus)
    if adj == "clair":
        s = 1.0 - (noir / 100.0)
        if clar == "clair": s = min(1.0, s + 0.15)
        return s
    if adj == "foncé":
        s = noir / 100.0
        if clar == "foncé": s = min(1.0, s + 0.15)
        return s
    if adj == "lumineux": return 1.0 if lumo == "lumineux" else 0.3 + 0.7 * (sat / 100.0)
    if adj == "mat":      return 1.0 if lumo == "mat" else 0.7 * (1.0 - sat / 100.0)
    return 0.0

def color_family_from_rgb(rgb_tuple):
    r, g, b = [c / 255.0 for c in rgb_tuple]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.05 or v < 0.1: return "grey"
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

df_view["s1"] = df_view.apply(lambda r: score_adjective(r, adj1), axis=1)
df_view["s2"] = df_view.apply(lambda r: score_adjective(r, adj2), axis=1)
df_view["s3"] = df_view.apply(lambda r: score_adjective(r, adj3), axis=1)

# =========================
# Tri de base (score + famille)
# =========================
w1, w2, w3 = 1.0, 0.6, 0.3

mask_strict = (
    (df_view["s1"] >= SEUIL_STRICT) &
    (df_view["s2"] >= SEUIL_STRICT) &
    (df_view["s3"] >= SEUIL_STRICT)
)

result = df_view.loc[mask_strict].copy()

# score global (toujours utile pour filtrer / info)
result["score_global"] = (
    w1*result["s1"] + w2*result["s2"] + w3*result["s3"]
) + 0.05*(result["saturation%"]/100.0)

# famille de couleur
result["famille"] = result["rgb"].apply(color_family_from_rgb)


if result.empty:
    st.info("Aucune couleur ne dépasse le seuil fixé pour les trois adjectifs. Modifie l’ordre/priorité ou choisis d’autres adjectifs.")
    st.stop()

def _rgb_to_hsv_tuple(rgb):
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h, s, v)
# =========================
# Ordre d'affichage par familles (comme le PDF)
# =========================
import math

if result.empty:
    st.info("Aucune couleur ne dépasse le seuil fixé pour les trois adjectifs. Modifie l’ordre/priorité ou choisis d’autres adjectifs.")
    st.stop()

# On ajoute H, S, V pour pouvoir trier finement
result[["H", "S", "V"]] = result["rgb"].apply(_rgb_to_hsv_tuple).apply(pd.Series)

PAGE_GROUPS = [
    ("Tons rosés", {"red", "magenta", "violet"}),
    ("Tons orangés/jaunes", {"orange", "yellow"}),
    ("Tons verts", {"green", "cyan"}),
    ("Tons bleus", {"blue"}),
    ("Tons neutres", {"grey", "other"}),
]

ordered_chunks = []

for _, fam_set in PAGE_GROUPS:
    df_group = result[result["famille"].isin(fam_set)].copy()
    if df_group.empty:
        continue

    # même logique que pour le PDF :
    if fam_set == {"grey", "other"}:
        df_group = df_group.sort_values(by=["V", "S"],
                                        ascending=[True, False]).reset_index(drop=True)
    else:
        df_group = df_group.sort_values(by=["H", "V", "S"],
                                        ascending=[True, True, False]).reset_index(drop=True)

    ordered_chunks.append(df_group)

# On concatène dans l'ordre des groupes pour construire l'ordre final d'affichage
if ordered_chunks:
    result = pd.concat(ordered_chunks, ignore_index=True)
else:
    # Par sécurité, même cas que plus haut
    st.info("Aucune couleur ne dépasse le seuil fixé pour les trois adjectifs. Modifie l’ordre/priorité ou choisis d’autres adjectifs.")
    st.stop()


# =========================
# Grille + pagination
# =========================
import math
def _latin1_safe(s: str) -> str:
    if s is None: return ""
    repl = {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "•": "-",
            "…": "...", "\u00A0": " "}
    for a, b in repl.items(): s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")

def swatch_card(row):
    r, g, b = row["rgb"]; hexcode = row["hex"]; ncs = row["ncs_code"]; nom = row.get("nom", "")
    st.markdown(
        f"""
        <div class="card">
          <div class="swatch" style="background: rgb({r},{g},{b});"></div>
          <div style="font-weight:700">{_latin1_safe(nom)}</div>
          <div style="font-size:12px; color:{THEME['muted']}; opacity:0.9">{ncs}</div>
        </div>
        """, unsafe_allow_html=True
    )
    st.text_input("HEX", value=hexcode, label_visibility="collapsed")

PAGE_SIZE = 36
total = int(len(result)); pages = max(1, math.ceil(total / PAGE_SIZE))
if "page" not in st.session_state: st.session_state.page = 1

col_prev, col_info, col_next = st.columns([1, 2, 1])
with col_prev:
    if st.button("◀︎ Précédent", use_container_width=True) and st.session_state.page > 1:
        st.session_state.page -= 1
with col_next:
    if st.button("Suivant ▶︎", use_container_width=True) and st.session_state.page < pages:
        st.session_state.page += 1
with col_info:
    st.markdown(f"<div style='text-align:center'>Page {st.session_state.page} / {pages}</div>", unsafe_allow_html=True)

page = st.session_state.page
start = (page - 1) * PAGE_SIZE; end = min(start + PAGE_SIZE, total)
chunk = result.iloc[start:end].copy()

cols_per_row = 6; rows = math.ceil(len(chunk) / cols_per_row)
for r in range(rows):
    cols = st.columns(cols_per_row)
    for j in range(cols_per_row):
        idx = r * cols_per_row + j
        if idx < len(chunk):
            with cols[j]:
                swatch_card(chunk.iloc[idx])

with st.expander("Voir la table détaillée"):
    st.dataframe(
        result[[
            "ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte",
            "temperature", "clarte", "luminosite", "famille", "score_global"
        ]],
        use_container_width=True
    )

# =========================
# PDF (logo bas-gauche + crédit)
# =========================
CREDIT_FOOTER = "Nuancier généré par Otto Amélie – Tous droits réservés"

class PDF(FPDF):
    def __init__(self, logo_path=None, credit=""):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.logo_path = logo_path
        self.credit = credit
        self.current_title = ""

    def header(self):
        self.set_font("Helvetica", size=14)
        self.set_text_color(62, 47, 42)
        self.set_xy(15, 12)
        self.cell(0, 8, _latin1_safe(self.current_title), ln=1)
        self.set_draw_color(164, 139, 120)
        self.set_line_width(0.6)
        self.line(15, 22, 195, 22)

    def footer(self):
        if self.logo_path:
            try:
                self.image(self.logo_path, x=15, y=282, w=35)
            except Exception:
                pass
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(107, 94, 86)
        self.cell(0, 8, _latin1_safe(self.credit), align='R')

def _rgb_to_hsv_tuple(rgb):
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h, s, v)

def generate_pdf_grouped_by_family_with_footer(dataframe: pd.DataFrame) -> bytes:
    df_pdf = dataframe.copy()
    if "rgb" not in df_pdf.columns:
        df_pdf["rgb"] = df_pdf["ncs_code"].apply(ncs_to_rgb)
    if "famille" not in df_pdf.columns:
        df_pdf["famille"] = df_pdf["rgb"].apply(color_family_from_rgb)
    df_pdf[["H", "S", "V"]] = df_pdf["rgb"].apply(_rgb_to_hsv_tuple).apply(pd.Series)

    PAGE_GROUPS = [
        ("Tons rosés", {"red", "magenta", "violet"}),
        ("Tons orangés/jaunes", {"orange", "yellow"}),
        ("Tons verts", {"green", "cyan"}),
        ("Tons bleus", {"blue"}),
        ("Tons neutres", {"grey", "other"}),
    ]

    pdf = PDF(logo_path=_pdf_logo_path, credit=CREDIT_FOOTER)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=9)

    left_margin, right_margin = 15, 15
    usable_width = 210 - left_margin - right_margin
    cols, swatch_h, gap_y = 3, 25, 10
    swatch_w = usable_width / cols
    start_y = 25
    bottom_limit = 297 - 15

    def add_group_pages(page_title: str, df_page: pd.DataFrame):
        pdf.current_title = page_title
        pdf.add_page()
        col = 0; x0 = left_margin; y = start_y
        for _, row in df_page.iterrows():
            needed = swatch_h + 3 + 10
            if y + needed > bottom_limit:
                pdf.current_title = f"{page_title} (suite)"
                pdf.add_page(); col = 0; y = start_y
            x = x0 + col * swatch_w
            r, g, b = row["rgb"]
            pdf.set_fill_color(int(r), int(g), int(b))
            pdf.rect(x, y, swatch_w, swatch_h, style='F')
            pdf.set_xy(x, y + swatch_h + 3)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(w=swatch_w, h=5, txt=_latin1_safe(str(row.get("nom", ""))), border=0, align='L')
            col += 1
            if col >= cols:
                col = 0
                y = pdf.get_y() + gap_y

    for page_title, fam_set in PAGE_GROUPS:
        df_group = df_pdf[df_pdf["famille"].isin(fam_set)].copy()
        if df_group.empty: continue
        if fam_set == {"grey", "other"}:
            df_group = df_group.sort_values(by=["V", "S"], ascending=[True, False]).reset_index(drop=True)
        else:
            df_group = df_group.sort_values(by=["H", "V", "S"], ascending=[True, True, False]).reset_index(drop=True)
        add_group_pages(page_title, df_group)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- Appel & bouton ---
pdf_bytes = generate_pdf_grouped_by_family_with_footer(result)
st.download_button(
    "Télécharger le PDF",
    data=pdf_bytes,
    file_name="nuancier_par_teintes.pdf",
    mime="application/pdf"
)

# Mention Streamlit (petit, en bas de page app)
st.caption("Produit développé par Otto Amélie")
