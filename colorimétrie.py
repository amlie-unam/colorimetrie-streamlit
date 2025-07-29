# -*- coding: utf-8 -*-
import streamlit as st
import csv
from fpdf import FPDF
import io

# ✅ Fonction pour charger le fichier CSV
@st.cache_data
def charger_couleurs(fichier):
    color_database = {}
    with open(fichier, encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) != 4:
                continue
            hex_code = "#" + row[0].strip().lstrip("#")  # s'assure que le # est présent
            profil = tuple(col.strip().lower() for col in row[1:4])
            color_database[hex_code] = profil
    return color_database

# 🔹 Charger les données depuis le fichier CSV
color_database = charger_couleurs("Colors.csv")

# 🖼️ Titre et instructions
st.title("🎨 Outil de Colorimétrie")
st.markdown("Entrez les **trois adjectifs** qui qualifient la personne, **dans l’ordre exact**.")

# 📝 Champs d'entrée utilisateur
adj1 = st.text_input("Premier adjectif").strip().lower()
adj2 = st.text_input("Deuxième adjectif").strip().lower()
adj3 = st.text_input("Troisième adjectif").strip().lower()

# 🔍 Recherche dans la base
if adj1 and adj2 and adj3:
    profil = (adj1, adj2, adj3)
    resultats = [code for code, attribs in color_database.items() if attribs == profil]

    if resultats:
        st.success("🎯 Couleurs correspondantes :")
        for code in resultats:
            st.color_picker(label=code, value=code, key=code)

        # 📄 Fonction pour générer le PDF
        def generate_pdf(profile, couleurs):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=14)
            pdf.cell(200, 10, txt=f"Profil colorimétrique : {', '.join(profile)}", ln=True)
            pdf.ln(10)
            for hex_code in couleurs:
                r = int(hex_code[1:3], 16)
                g = int(hex_code[3:5], 16)
                b = int(hex_code[5:7], 16)
                pdf.set_fill_color(r, g, b)
                pdf.cell(20, 10, '', fill=True)
                pdf.cell(40, 10, hex_code, ln=True)
            return pdf.output(dest='S').encode('latin-1')

        # ⬇️ Bouton de téléchargement du PDF
        pdf_data = generate_pdf(profil, resultats)
        st.download_button(
            label="📄 Télécharger la palette en PDF",
            data=pdf_data,
            file_name="palette_colorimetrie.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("❌ Aucune couleur trouvée pour cette combinaison exacte.")
