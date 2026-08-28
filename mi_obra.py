import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import plotly.express as px
import plotly.graph_objects as go
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
import io
import os
import base64

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="ERP de Arquitectura y Dirección de Obra", 
    layout="wide",
    initial_sidebar_state="expanded"
)

UPLOAD_DIR = "archivos_obra"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- BASE DE DATOS LOCAL ---
conn = sqlite3.connect("control_obras.db", check_same_thread=False, timeout=10)
cursor = conn.cursor()

# Tablas de Usuarios y Control de Acceso
cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE,
        password TEXT,
        rol TEXT,
        obra_id INTEGER
    )
""")
# Crear usuario Arquitecto maestro por defecto si no existe
cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'Arquitecto'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO usuarios (usuario, password, rol, obra_id) VALUES ('admin', 'admin123', 'Arquitecto', 0)")
    conn.commit()

# Tablas Maestras
cursor.execute("CREATE TABLE IF NOT EXISTS obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, codigo TEXT, presupuesto_total REAL)")
try: cursor.execute("ALTER TABLE obras ADD COLUMN estado_expediente TEXT DEFAULT 'En Curso / Activo'")
except sqlite3.OperationalError: pass
try: cursor.execute("ALTER TABLE obras ADD COLUMN honorarios_base REAL DEFAULT 12000.0")
except sqlite3.OperationalError: pass
try: cursor.execute("ALTER TABLE obras ADD COLUMN superficie_construida REAL DEFAULT 120.0")
except sqlite3.OperationalError: pass

cursor.execute("CREATE TABLE IF NOT EXISTS honorarios (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fase TEXT, porcentaje REAL, base_imponible REAL, iva REAL, retencion_irpf REAL, total_a_cobrar REAL, estado TEXT, fecha_emision TEXT, fecha_cobro TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS tramites (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, organismo TEXT, tipo_tramite TEXT, num_expediente TEXT, fecha_solicitud TEXT, fecha_limite TEXT, tasas_euros REAL, estado TEXT, observaciones TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS licitaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, capitulo TEXT, presupuesto_estimado REAL, empresa_a TEXT, oferta_a REAL, empresa_b TEXT, oferta_b REAL, empresa_c TEXT, oferta_c REAL, empresa_adjudicada TEXT, monto_adjudicado REAL, estado TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS certificaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, num_certificacion INTEGER, mes_ano TEXT, importe_bruto REAL, retencion_5pct REAL, liquido_pagar REAL, iva_21 REAL, total_factura REAL, estado TEXT, fecha_aprobacion TEXT, observaciones TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS cierre_obra (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER UNIQUE, fecha_cfo TEXT, fecha_acta_recepcion TEXT, estado_cierre TEXT, retencion_devuelta TEXT, fecha_devolucion_retencion TEXT, observaciones TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS posventa (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha_aviso TEXT, elemento_afectado TEXT, descripcion TEXT, responsable TEXT, estado TEXT, fecha_resolucion TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS incidencias (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha TEXT, descripcion TEXT, rol_emisor TEXT, prioridad TEXT, estado TEXT, foto_path TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS cronograma (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, etapa TEXT, tarea TEXT, fecha_inicio TEXT, fecha_fin TEXT, coste_estimado REAL, avance_porcentaje INTEGER DEFAULT 0, responsable TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS documentos (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha_entrega TEXT, tipo_doc TEXT, codigo_plano TEXT, revision TEXT, destinatario TEXT, descripcion TEXT, archivo_path TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS anteproyectos (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, titulo TEXT, archivo_path TEXT, fecha TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS buzon_cliente (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha TEXT, emisor TEXT, mensaje TEXT)")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS ingenieria_datos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER UNIQUE, tipo_terreno TEXT, tension_adm REAL, 
        nivel_freatico REAL, sismicidad TEXT, tipo_cimentacion_sugerida TEXT, superficie_m2 REAL, 
        plantas_sobre_rasante INTEGER, luz_maxima_m TEXT, hormigon_fck TEXT, acero_fyk TEXT, observaciones TEXT,
        coste_geotecnico REAL, archivo_geo TEXT, realizado_por_est TEXT, coste_estructuras REAL, archivo_est TEXT
    )
""")
try: cursor.execute("ALTER TABLE ingenieria_datos ADD COLUMN coste_geotecnico REAL DEFAULT 0.0")
except sqlite3.OperationalError: pass
try: cursor.execute("ALTER TABLE ingenieria_datos ADD COLUMN archivo_geo TEXT")
except sqlite3.OperationalError: pass
try: cursor.execute("ALTER TABLE ingenieria_datos ADD COLUMN realizado_por_est TEXT")
except sqlite3.OperationalError: pass
try: cursor.execute("ALTER TABLE ingenieria_datos ADD COLUMN coste_estructuras REAL DEFAULT 0.0")
except sqlite3.OperationalError: pass
try: cursor.execute("ALTER TABLE ingenieria_datos ADD COLUMN archivo_est TEXT")
except sqlite3.OperationalError: pass

# Tabla para el buzón exclusivo entre Cliente y Arquitecto
cursor.execute("CREATE TABLE IF NOT EXISTS buzon_cliente (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha TEXT, emisor TEXT, mensaje TEXT)")

conn.commit()

# --- DATOS Y COEFICIENTES COAC ---
MODULO_BASICO_COAC = 677
coef_ubicacion = {"Cerdanya / Vall d'Aran / Alt Urgell / Resto de Barcelona (0.95)": 0.95, "Barcelona Ciudad y metropolitana (1.00)": 1.00, "Girona / Tarragona / Lleida (0.95)": 0.95, "Comarcas Lleida / Tierras del Ebro (0.90)": 0.90}
coef_tipologia = {"Obra Nueva aislada (1.20)": 1.20, "Obra Nueva entre medianeras (1.00)": 1.00, "Rehabilitación integral (0.90)": 0.90, "Reforma que afectan estructuras (0.70)": 0.70, "Reforma que no afectan estructuras (0.58)": 0.58, "Reforma leve (pintura, acabados) (0.30)": 0.30}
coef_uso = {"Vivienda / Residencial (unifamiliares, bloques y pareados) (1.00)": 1.00, "Oficinas y Administrativo (1.00)": 1.00, "Comercial / Locales (1.20)": 1.20, "Industrial / Almacenes (0.60)": 0.60, "Dotacional (Sanitario, Educativo) (1.10)": 1.10}
coef_calidad = {"Económico (0.85)": 0.85, "Estándar (1.00)": 1.00, "Premium (1.20)": 1.20}

# --- GENERADORES DE PDF ---
def dibujar_membrete_corporativo(canvas, doc):
    canvas.saveState()
    c_negro = colors.HexColor("#1A1A1A")
    c_gris_oscuro = colors.HexColor("#4A5568")
    c_gris_claro = colors.HexColor("#E2E8F0")
    canvas.setFillColor(c_negro)
    canvas.rect(0, A4[1] - 1.2*cm, A4[0], 1.2*cm, fill=1, stroke=0)
    canvas.setFillColor(c_gris_oscuro)
    canvas.rect(0, A4[1] - 1.4*cm, A4[0], 0.2*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(1.5*cm, A4[1] - 0.8*cm, "ESTUDIO DE ARQUITECTURA & GESTIÓN DE OBRA")
    canvas.setFillColor(c_gris_claro)
    canvas.rect(0, 0, A4[0], 0.8*cm, fill=1, stroke=0)
    canvas.setFillColor(c_negro)
    canvas.rect(0, 0.8*cm, A4[0], 0.1*cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(c_gris_oscuro)
    canvas.drawString(1.5*cm, 0.3*cm, "Documento Técnico Oficial - Expediente Consolidado")
    canvas.drawRightString(A4[0] - 1.5*cm, 0.3*cm, f"Página {doc.page}")
    canvas.restoreState()

def generar_expediente_maestro_pdf(datos_obra, df_hon, df_tra, df_lic, df_cer, cierre_row):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=55, bottomMargin=50)
    story = []
    styles = getSampleStyleSheet()
    c_primary = colors.HexColor("#1A1A1A")
    c_secondary = colors.HexColor("#4A5568")
    c_text = colors.HexColor("#2D3748")
    t_style = ParagraphStyle("TitleDoc", parent=styles["Heading1"], fontSize=14, textColor=c_primary, spaceAfter=4, alignment=1, fontName="Helvetica-Bold")
    sub_style = ParagraphStyle("SubDoc", parent=styles["Heading2"], fontSize=10, textColor=c_secondary, spaceBefore=8, spaceAfter=3, fontName="Helvetica-Bold")
    n_style = ParagraphStyle("NormDoc", parent=styles["Normal"], fontSize=8.5, textColor=c_text, leading=11)
    n_bold = ParagraphStyle("NormBold", parent=n_style, fontName="Helvetica-Bold")

    story.append(Spacer(1, 5))
    story.append(Paragraph("DOSSIER DE EXPEDIENTE MAESTRO - RESUMEN EJECUTIVO", t_style))
    story.append(Paragraph(f"<b>Referencia:</b> {datos_obra['codigo']} &nbsp;|&nbsp; <b>Proyecto:</b> {datos_obra['nombre']} &nbsp;|&nbsp; <b>Estado:</b> {datos_obra.get('estado_expediente', 'En Curso')}", ParagraphStyle("SubHead", parent=n_style, alignment=1)))
    story.append(Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%d/%m/%Y')}", ParagraphStyle("SubHead2", parent=n_style, alignment=1)))
    story.append(Spacer(1, 8))

    story.append(Paragraph("1. FASE 1 - Honorarios y Propuesta Comercial", sub_style))
    if not df_hon.empty:
        tot_hon = df_hon["base_imponible"].sum()
        data_h = [["Fase / Servicio", "Base (€)", "Total (€)", "Estado"]]
        for _, r in df_hon.iterrows():
            data_h.append([Paragraph(r["fase"], n_style), f"{r['base_imponible']:,.2f}", f"{r['total_a_cobrar']:,.2f}", r["estado"]])
        t_h = Table(data_h, colWidths=[200, 80, 80, 150])
        t_h.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), c_primary), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 8), ('ALIGN', (1,1), (2,-1), 'RIGHT'), ('BOTTOMPADDING', (0,0), (-1,-1), 3), ('TOPPADDING', (0,0), (-1,-1), 3)]))
        story.append(t_h)
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<b>Base Total Acumulada en Honorarios:</b> {tot_hon:,.2f} €", n_bold))
    else:
        story.append(Paragraph("Sin honorarios registrados.", n_style))

    story.append(Paragraph("2. FASE 2 - Gestión Municipal y Tasas", sub_style))
    if not df_tra.empty:
        tot_tasas = df_tra["tasas_euros"].sum()
        data_t = [["Organismo", "Tipo de Trámite", "Nº Exp", "Tasas (€)", "Estado"]]
        for _, r in df_tra.iterrows():
            data_t.append([Paragraph(r["organismo"], n_style), Paragraph(r["tipo_tramite"], n_style), r["num_expediente"], f"{r['tasas_euros']:,.2f}", r["estado"]])
        t_t = Table(data_t, colWidths=[130, 140, 80, 70, 90])
        t_t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), c_secondary), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 8), ('ALIGN', (3,1), (3,-1), 'RIGHT'), ('BOTTOMPADDING', (0,0), (-1,-1), 3), ('TOPPADDING', (0,0), (-1,-1), 3)]))
        story.append(t_t)
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<b>Total Tasas e Impuestos Abonados:</b> {tot_tasas:,.2f} €", n_bold))
    else:
        story.append(Paragraph("Sin trámites registrados.", n_style))

    story.append(Paragraph("3. FASE 3 - Contratas y Licitación", sub_style))
    story.append(Paragraph(f"Presupuesto de Ejecución de Contrata (PEC Asignado): <b>{datos_obra['presupuesto_total']:,.2f} €</b>", n_style))
    if not df_lic.empty:
        data_l = [["Capítulo / Paquete", "PEM Est. (€)", "Empresa Adjudicataria", "Importe Adjudicado (€)"]]
        for _, r in df_lic.iterrows():
            data_l.append([Paragraph(r["capitulo"], n_style), f"{r['presupuesto_estimado']:,.2f}", Paragraph(r["empresa_adjudicada"], n_style), f"{r['monto_adjudicado']:,.2f}"])
        t_l = Table(data_l, colWidths=[170, 85, 125, 130])
        t_l.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), c_primary), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 8), ('ALIGN', (1,1), (1,-1), 'RIGHT'), ('ALIGN', (3,1), (3,-1), 'RIGHT'), ('BOTTOMPADDING', (0,0), (-1,-1), 3), ('TOPPADDING', (0,0), (-1,-1), 3)]))
        story.append(t_l)

    story.append(Paragraph("4. FASE 4 - Ejecución y Certificaciones", sub_style))
    if not df_cer.empty:
        tot_cer = df_cer["importe_bruto"].sum()
        data_c = [["Nº", "Periodo", "Importe Bruto (€)", "Ret. 5% (€)", "Líquido (€)", "Estado"]]
        for _, r in df_cer.iterrows():
            data_c.append([f"#{r['num_certificacion']}", r["mes_ano"], f"{r['importe_bruto']:,.2f}", f"{r['retencion_5pct']:,.2f}", f"{r['liquido_pagar']:,.2f}", r["estado"]])
        t_c = Table(data_c, colWidths=[25, 100, 95, 80, 90, 120])
        t_c.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), c_secondary), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 8), ('ALIGN', (2,1), (4,-1), 'RIGHT'), ('BOTTOMPADDING', (0,0), (-1,-1), 3), ('TOPPADDING', (0,0), (-1,-1), 3)]))
        story.append(t_c)
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<b>Total Certificado a Origen:</b> {tot_cer:,.2f} €", n_bold))
    else:
        story.append(Paragraph("Sin certificaciones de obra emitidas.", n_style))

    doc.build(story, onFirstPage=dibujar_membrete_corporativo, onLaterPages=dibujar_membrete_corporativo)
    buffer.seek(0)
    return buffer

def generar_propuesta_pdf(datos_obra, df_honorarios):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle("Titulo", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#1A1A1A"), spaceAfter=10, alignment=1)
    subtitulo_style = ParagraphStyle("Subtitulo", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#4A5568"), spaceAfter=6)
    normal_style = styles["Normal"]

    story.append(Paragraph("PROPUESTA DE SERVICIOS PROFESIONALES", titulo_style))
    story.append(Spacer(1, 15))
    story.append(Paragraph(f"<b>Referencia de Proyecto:</b> {datos_obra['codigo']} - {datos_obra['nombre']}", normal_style))
    story.append(Paragraph(f"<b>Fecha de Propuesta:</b> {datetime.now().strftime('%d/%m/%Y')}", normal_style))
    story.append(Paragraph(f"<b>Presupuesto Estimado de Ejecución Material (PEM):</b> {datos_obra['presupuesto_total']:,.2f} €", normal_style))
    story.append(Spacer(1, 20))

    story.append(Paragraph("1. Desglose de Honorarios y Servicios", subtitulo_style))
    if not df_honorarios.empty:
        data_hon = [["Fase de Trabajo / Servicio", "Base Imponible", "IVA", "IRPF", "Total a Abonar"]]
        for _, r_h in df_honorarios.iterrows():
            if "Visita Inicial" in r_h["fase"]: continue
            data_hon.append([r_h["fase"], f"{r_h['base_imponible']:,.2f} €", f"{r_h['iva']:,.2f} €", f"{r_h['retencion_irpf']:,.2f} €", f"{r_h['total_a_cobrar']:,.2f} €"])
        t_hon = Table(data_hon, colWidths=[200, 85, 60, 60, 95])
        t_hon.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")), ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (1, 1), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(t_hon)
    else:
        story.append(Paragraph("Pendiente de calcular.", normal_style))
    
    story.append(Spacer(1, 40))
    story.append(Paragraph("2. Aceptación de la Propuesta", subtitulo_style))
    story.append(Paragraph("La firma del presente documento supone la aceptación del presupuesto detallado y autoriza el inicio de los trabajos correspondientes a la redacción del proyecto.", normal_style))
    story.append(Spacer(1, 50))
    
    data_firmas = [["Fdo: El Arquitecto", "Fdo: El Promotor / Cliente"], ["", ""], ["___________________________", "___________________________"]]
    t_firmas = Table(data_firmas, colWidths=[250, 250])
    t_firmas.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold')]))
    story.append(t_firmas)
    doc.build(story)
    buffer.seek(0)
    return buffer

def generar_informe_coac_pdf(nombre_obra, codigo_obra, cliente, municipio, sup, pem, honorarios, porc, cu):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=3*cm)
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1a252f'))
    style_section = ParagraphStyle('SecTitle', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor('#1a252f'), spaceBefore=10, spaceAfter=6)
    style_body = ParagraphStyle('DocBody', parent=styles['Normal'], fontSize=9.5, leading=13.5)
    style_body_bold = ParagraphStyle('DocBodyBold', parent=style_body, fontName='Helvetica-Bold')
    eur = lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"

    def dibujar_pie_pagina(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 9)
        canvas.setStrokeColor(colors.grey)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 2.5*cm, doc.width + doc.leftMargin, 2.5*cm)
        canvas.drawString(doc.leftMargin, 1.8*cm, "Lugar y Fecha: ________________________________")
        canvas.drawRightString(doc.width + doc.leftMargin, 1.8*cm, "Firma del Profesional: ________________________________")
        canvas.drawCentredString(A4[0]/2, 1*cm, f"Página {doc.page}")
        canvas.restoreState()

    contenido = [Paragraph("INFORME DE VALORACIÓN ECONÓMICA (COAC)", style_title), Spacer(1, 4)]
    t_line = Table([[""]], colWidths=[530], rowHeights=[2])
    t_line.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1a252f'))]))
    contenido.append(t_line)
    contenido.append(Spacer(1, 15))

    datos_bloque = [
        [Paragraph("<b>DATOS DEL ENCARGO</b>", style_body_bold), Paragraph("<b>PARÁMETROS DE CÁLCULO</b>", style_body_bold)],
        [Paragraph(f"<b>Proyecto:</b> {nombre_obra}", style_body), Paragraph(f"<b>Superficie:</b> {sup:,.1f} m²", style_body)],
        [Paragraph(f"<b>Cliente:</b> {cliente}", style_body), Paragraph(f"<b>Módulo Base:</b> {MODULO_BASICO_COAC} €/m²", style_body)],
        [Paragraph(f"<b>Municipio:</b> {municipio}", style_body), Paragraph(f"<b>Uso (CU):</b> {cu:.2f}", style_body)],
        [Paragraph(f"<b>Referencia:</b> {codigo_obra}", style_body), Paragraph("", style_body)]
    ]
    t_datos = Table(datos_bloque, colWidths=[265, 265])
    t_datos.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
    contenido.append(t_datos)
    contenido.append(Spacer(1, 15))

    pec_estimado = pem * 1.19
    iva = honorarios * 0.21
    total = honorarios + iva
    contenido.append(Paragraph("RESUMEN DE VALORACIÓN ECONÓMICA", style_section))
    data_fin = [
        [Paragraph("<font color='white'><b>CONCEPTO BASE</b></font>", style_body_bold), Paragraph("<font color='white'><b>VALOR ESTIMADO</b></font>", style_body_bold)],
        ["Presupuesto Ejecución Material (P.E.M.)", eur(pem)],
        ["Presupuesto Ejecución Contrata (P.E.C.)", eur(pec_estimado)],
        [f"Honorarios Profesionales ({int(porc*100)}%)", Paragraph(f"<b>{eur(honorarios)}</b>", style_body)],
        ["I.V.A. Aplicable (21%)", eur(iva)],
        [Paragraph("<font color='#d9534f'><b>TOTAL PROPUESTA (Neto + IVA)</b></font>", style_body_bold), Paragraph(f"<font color='#d9534f'><b>{eur(total)}</b></font>", style_body_bold)]
    ]
    t_fin = Table(data_fin, colWidths=[380, 150])
    t_fin.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a252f')), ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (1,1), (1,-1), 'RIGHT'), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
    contenido.append(t_fin)
    contenido.append(Spacer(1, 15))

    doc.build(contenido, onFirstPage=dibujar_pie_pagina, onLaterPages=dibujar_pie_pagina)
    buffer.seek(0)
    return buffer

def generar_informe_tecnico_pdf(datos_obra, ing_row):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = [Paragraph("MEMORIA TÉCNICA DE PREDIMENSIONADO", ParagraphStyle("Titulo", parent=getSampleStyleSheet()["Heading1"], fontSize=18, textColor=colors.HexColor("#1A1A1A"), alignment=1)), Spacer(1, 15)]
    story.append(Paragraph(f"<b>Proyecto:</b> {datos_obra['nombre']} | <b>Referencia:</b> {datos_obra['codigo']}", getSampleStyleSheet()["Normal"]))
    story.append(Spacer(1, 20))
    if ing_row is not None:
        data_geo = [
            ["Clasificación del Terreno", str(ing_row["tipo_terreno"])],
            ["Tensión Admisible (σ_adm)", f"{ing_row['tension_adm']} kg/cm²"],
            ["Nivel Freático", f"{ing_row['nivel_freatico']} m" if float(ing_row['nivel_freatico']) != -1 else "No detectado"],
            ["Cimentación Sugerida", str(ing_row["tipo_cimentacion_sugerida"])]
        ]
        t_geo = Table(data_geo, colWidths=[200, 250])
        t_geo.setStyle(TableStyle([('BACKGROUND', (0,0), (0,-1), colors.HexColor("#E2E8F0")), ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        story.append(t_geo)
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- GESTIÓN DE ESTADO Y PANTALLA DE LOGIN ---
if "app_iniciada" not in st.session_state: st.session_state["app_iniciada"] = False
if "rol_usuario" not in st.session_state: st.session_state["rol_usuario"] = None
if "obra_asignada" not in st.session_state: st.session_state["obra_asignada"] = None

if not st.session_state["app_iniciada"] or st.session_state["rol_usuario"] is None:
    st.markdown("""
        <style>
    /* Ocultar elementos nativos de Streamlit */
    [data-testid="stSidebarNav"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown("<div class='main-block'>", unsafe_allow_html=True)
        logo_path = "logo_estudio.png"
        if os.path.exists(logo_path):
            st.image(logo_path, width=650) # Mantuve el ancho de 650 que ajustaste anteriormente
        else:
            st.markdown("<h1 style='color: white; text-align: center;'>ESTUDIO DE ARQUITECTURA</h1>", unsafe_allow_html=True)
        
        # Nuevo texto con espaciado elegante
        st.markdown("<br><h3 style='color: white; text-align: center; font-family: Helvetica, sans-serif; font-weight: 300; letter-spacing: 5px;'>ESTUDIO DE ARQUITECTURA TAL</h3><br>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            usr = st.text_input("Usuario")
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("ACCEDER AL DESPACHO", use_container_width=True):
                cursor.execute("SELECT rol, obra_id FROM usuarios WHERE usuario=? AND password=?", (usr, pwd))
                res = cursor.fetchone()
                if res:
                    st.session_state["rol_usuario"] = res[0]
                    st.session_state["obra_asignada"] = res[1]
                    st.session_state["app_iniciada"] = True
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- CSS DE LA APLICACIÓN (HOVER BARRA LATERAL) ---
st.markdown("""
    <style>
    /* Ocultar elementos nativos de Streamlit */
    [data-testid="stSidebarNav"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Fondo principal oscuro profundo */
    .stApp { background-color: #0d0d0d !important; }

    /* Tipografía (Aplicada solo al texto, SIN romper los iconos) */
    html, body {
        font-family: 'Helvetica Neue', sans-serif !important;
    }
    
    /* Color de texto general claro */
    [class*="st-"] {
        color: #E2E8F0 !important;
    }

    /* Estilo forzado para campos de texto (Inputs y Textareas) */
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > textarea {
        background-color: #2b2b2b !important; /* Fondo gris oscuro */
        color: #ffffff !important; /* Letra blanca */
        border: 1px solid #4a4a4a !important; /* Borde sutil */
        border-radius: 8px !important;
    }

    /* Asegurar que el placeholder (texto de fondo) se lea bien */
    div[data-baseweb="input"] > div::placeholder,
    div[data-baseweb="textarea"] > textarea::placeholder {
        color: #a0aabf !important;
    }
    
    /* Diseño de Tarjetas para los Expanders */
    div[data-testid="stExpander"] {
        background-color: #1a1a1a !important;
        border: 1px solid #2d2d2d !important;
        border-radius: 16px !important;
        margin-bottom: 15px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
    }

    /* Botones redondeados y modernos */
    div.stButton > button {
        background-color: #2b2b2b !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 20px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1.2rem !important;
        transition: all 0.3s ease !important;
    }
    
    div.stButton > button:hover {
        background-color: #404040 !important;
        transform: translateY(-2px);
    }

    /* Cajas de métricas */
    [data-testid="stMetric"] {
        background-color: #1a1a1a !important;
        border-radius: 12px !important;
        padding: 15px !important;
        border: 1px solid #2d2d2d !important;
    }

    /* Barra lateral colapsable */
    [data-testid="stSidebar"] {
        background-color: #121212 !important;
        min-width: 15px !important;
        max-width: 15px !important;
        transition: all 0.3s ease-in-out 0.5s !important;
        overflow-x: hidden !important;
        border-right: 1px solid #2d2d2d !important;
    }
    
    [data-testid="stSidebar"]:hover, [data-testid="stSidebar"]:focus-within {
        min-width: 320px !important;
        max-width: 320px !important;
        transition: all 0.3s ease-in-out 0s !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

rol = st.session_state["rol_usuario"]

# --- BARRA LATERAL ---
logo_path = "logo_estudio.png"
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
else:
    st.sidebar.markdown("<h3 style='text-align: center; color: white;'>TAL Arquitectura</h3>", unsafe_allow_html=True)

if st.sidebar.button("⬅️ Cerrar Sesión", use_container_width=True):
    st.session_state["app_iniciada"] = False
    st.session_state["rol_usuario"] = None
    st.session_state["obra_asignada"] = None
    st.rerun()

st.sidebar.markdown(f"👤 **Perfil Activo:** {rol}")
st.sidebar.divider()

if rol == "Arquitecto":
    with st.sidebar.expander("➕ Crear Nuevo Proyecto"):
        with st.form("form_nueva_obra", clear_on_submit=True):
            nuevo_nombre = st.text_input("Nombre del Proyecto:")
            nuevo_codigo = st.text_input("Código de Encargo:")
            nuevo_presupuesto = st.number_input("Presupuesto Ejecución Contrata (€):", min_value=0.0, step=5000.0, value=150000.0)
            if st.form_submit_button("Crear Proyecto") and nuevo_nombre.strip() != "":
                try:
                    cursor.execute("INSERT INTO obras (nombre, codigo, presupuesto_total, estado_expediente, honorarios_base, superficie_construida) VALUES (?, ?, ?, 'En Curso / Activo', 12000.0, 120.0)", (nuevo_nombre, nuevo_codigo, nuevo_presupuesto))
                    conn.commit()
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.sidebar.error("Ya existe un proyecto con ese nombre.")

# === FILTRO DINÁMICO DE OBRAS ===
if rol == "Arquitecto":
    obras_df = pd.read_sql_query("SELECT * FROM obras", conn)
else:
    obra_id_permitida = st.session_state["obra_asignada"]
    obras_df = pd.read_sql_query("SELECT * FROM obras WHERE id = ?", conn, params=(obra_id_permitida,))

if obras_df.empty:
    st.info("👈 No hay obras disponibles para tu usuario.")
    st.stop()

opciones_obras = {f"{row['codigo']} - {row['nombre']}": row['id'] for _, row in obras_df.iterrows()}
obra_seleccionada_txt = st.sidebar.selectbox("Proyecto Activo:", list(opciones_obras.keys()))
obra_id_activa = opciones_obras[obra_seleccionada_txt]
datos_obra = obras_df[obras_df['id'] == obra_id_activa].iloc[0]

sup_guardada = float(datos_obra.get('superficie_construida', 120.0))
if pd.isna(sup_guardada): sup_guardada = 120.0
hon_guardados = float(datos_obra.get('honorarios_base', 12000.0))
if pd.isna(hon_guardados): hon_guardados = 12000.0

if rol == "Arquitecto":
    with st.sidebar.expander("✏️ Modificar Datos y Estado de Archivo"):
        with st.form("form_editar_obra"):
            edit_nombre_obra = st.text_input("Nombre:", value=datos_obra['nombre'])
            edit_codigo_obra = st.text_input("Código:", value=datos_obra['codigo'])
            edit_presupuesto_base = st.number_input("Presupuesto Ejecución (€):", value=float(datos_obra['presupuesto_total']), step=1000.0)
            estados_posibles = ["En Curso / Activo", "Finalizado en Fase Intermedia (Ej: Solo Básico)", "Obra Concluida / Cerrada"]
            estado_actual_db = datos_obra.get('estado_expediente', 'En Curso / Activo')
            idx_est = estados_posibles.index(estado_actual_db) if estado_actual_db in estados_posibles else 0
            edit_estado_exp = st.selectbox("Estado del Expediente:", estados_posibles, index=idx_est)
            if st.form_submit_button("Actualizar y Archivar"):
                cursor.execute("UPDATE obras SET nombre = ?, codigo = ?, presupuesto_total = ?, estado_expediente = ? WHERE id = ?", (edit_nombre_obra, edit_codigo_obra, edit_presupuesto_base, edit_estado_exp, obra_id_activa))
                conn.commit()
                st.rerun()

    with st.sidebar.expander("🔐 Gestión de Accesos (Clientes/Constructores)"):
        st.write(f"Dar acceso a: **{datos_obra['nombre']}**")
        with st.form("form_accesos", clear_on_submit=True):
            n_usr = st.text_input("Usuario (Ej: cliente_01):")
            n_pwd = st.text_input("Contraseña:")
            n_rol = st.selectbox("Rol:", ["Cliente", "Constructor"])
            if st.form_submit_button("Crear Acceso a esta Obra"):
                if n_usr and n_pwd:
                    try:
                        cursor.execute("INSERT INTO usuarios (usuario, password, rol, obra_id) VALUES (?, ?, ?, ?)", (n_usr, n_pwd, n_rol, obra_id_activa))
                        conn.commit()
                        st.sidebar.success("Usuario creado.")
                    except sqlite3.IntegrityError:
                        st.sidebar.error("El nombre de usuario ya existe.")

    with st.sidebar.expander("📐 Calculadora COAC Express", expanded=False):
        st.caption(f"Módulo Básico COAC: **{MODULO_BASICO_COAC} €/m²**")
        c_sup = st.number_input("Superficie Construida (m²):", min_value=1.0, value=sup_guardada, step=10.0, key="coac_sup")
        c_ub = st.selectbox("Ubicación (CG):", list(coef_ubicacion.keys()), index=0, key="coac_ub")
        c_tip = st.selectbox("Tipo de Obra (CT):", list(coef_tipologia.keys()), index=4, key="coac_tip")
        c_uso = st.selectbox("Uso (CU):", list(coef_uso.keys()), index=0, key="coac_uso")
        c_cal = st.selectbox("Calidad (CQ):", list(coef_calidad.keys()), index=1, key="coac_cal")
        cg_val = coef_ubicacion[c_ub]
        ct_val = coef_tipologia[c_tip]
        cu_val = coef_uso[c_uso]
        cq_val = coef_calidad[c_cal]
        
        pem_coac_calc = c_sup * MODULO_BASICO_COAC * cg_val * ct_val * cq_val * cu_val
        porc_hon_coac = 0.12 if pem_coac_calc < 50000 else 0.10
        hon_coac_calc = pem_coac_calc * porc_hon_coac
        pec_coac_calc = pem_coac_calc * 1.19

        st.markdown("---")
        st.write(f"**PEM Estimado:** `{pem_coac_calc:,.2f} €`")
        st.write(f"**PEC Contrata (19%):** `{pec_coac_calc:,.2f} €`")
        st.success(f"**Honorarios ({int(porc_hon_coac*100)}%):** {hon_coac_calc:,.2f} €")

        col_btn_c1, col_btn_c2 = st.columns(2)
        with col_btn_c1:
            if st.button("📥 Aplicar PEC", use_container_width=True):
                cursor.execute("UPDATE obras SET presupuesto_total = ?, honorarios_base = ?, superficie_construida = ? WHERE id = ?", (round(pec_coac_calc, 2), round(hon_coac_calc, 2), c_sup, obra_id_activa))
                conn.commit()
                st.rerun()
        with col_btn_c2:
            pdf_coac_bytes = generar_informe_coac_pdf(datos_obra["nombre"], datos_obra["codigo"], "D. Cliente Promotor", "Cataluña", c_sup, pem_coac_calc, hon_coac_calc, porc_hon_coac, cu_val)
            st.download_button(label="📄 PDF COAC", data=pdf_coac_bytes, file_name=f"Valoracion_COAC_{datos_obra['codigo']}.pdf", mime="application/pdf", use_container_width=True)

# --- CONSULTAS DE DATOS ---
df_honorarios = pd.read_sql_query("SELECT * FROM honorarios WHERE obra_id = ?", conn, params=(obra_id_activa,))
df_tramites = pd.read_sql_query("SELECT * FROM tramites WHERE obra_id = ?", conn, params=(obra_id_activa,))
df_licit = pd.read_sql_query("SELECT * FROM licitaciones WHERE obra_id = ?", conn, params=(obra_id_activa,))
df_cert = pd.read_sql_query("SELECT * FROM certificaciones WHERE obra_id = ? ORDER BY num_certificacion ASC", conn, params=(obra_id_activa,))
df_gantt = pd.read_sql_query("SELECT * FROM cronograma WHERE obra_id = ?", conn, params=(obra_id_activa,))
df_inc = pd.read_sql_query("SELECT * FROM incidencias WHERE obra_id = ? ORDER BY id DESC", conn, params=(obra_id_activa,))
df_docs = pd.read_sql_query("SELECT * FROM documentos WHERE obra_id = ? ORDER BY id DESC", conn, params=(obra_id_activa,))
df_cierre = pd.read_sql_query("SELECT * FROM cierre_obra WHERE obra_id = ?", conn, params=(obra_id_activa,))
df_posventa = pd.read_sql_query("SELECT * FROM posventa WHERE obra_id = ? ORDER BY id DESC", conn, params=(obra_id_activa,))
df_ing = pd.read_sql_query("SELECT * FROM ingenieria_datos WHERE obra_id = ?", conn, params=(obra_id_activa,))
df_anteproyectos = pd.read_sql_query("SELECT * FROM anteproyectos WHERE obra_id = ? ORDER BY id DESC", conn, params=(obra_id_activa,))

total_previsto = df_gantt["coste_estimado"].sum() if not df_gantt.empty else 0.0
total_fisico_euros = (df_gantt["coste_estimado"] * (df_gantt["avance_porcentaje"] / 100.0)).sum() if not df_gantt.empty else 0.0
pct_fisico_global = (total_fisico_euros / total_previsto * 100) if total_previsto > 0 else 0.0
total_cert_bruto = df_cert["importe_bruto"].sum() if not df_cert.empty else 0.0
pct_financiero_global = (total_cert_bruto / datos_obra["presupuesto_total"] * 100) if datos_obra["presupuesto_total"] > 0 else 0.0
total_retenciones = df_cert["retencion_5pct"].sum() if not df_cert.empty else 0.0
total_abonado_liquido = df_cert[df_cert["estado"] == "Abonada / Pagada"]["liquido_pagar"].sum() if not df_cert.empty else 0.0
pendiente_certificar = max(0.0, total_fisico_euros - total_cert_bruto)
total_honorarios_base = df_honorarios["base_imponible"].sum() if not df_honorarios.empty else 0.0
total_tasas_pagadas = df_tramites["tasas_euros"].sum() if not df_tramites.empty else 0.0
inversion_total_cliente = datos_obra["presupuesto_total"] + total_honorarios_base + total_tasas_pagadas

# --- CABECERA PRINCIPAL Y ÚNICO BOTÓN MAESTRO DE DESCARGA ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.title(f"Proyecto: {datos_obra['nombre']}")
    est_exp = datos_obra.get('estado_expediente', 'En Curso / Activo')
    if rol == "Arquitecto":
        st.caption(f"Ref: {datos_obra['codigo']} | Estado: **{est_exp}** | Inversión Total Cliente: **{inversion_total_cliente:,.2f} €** (Obra: {datos_obra['presupuesto_total']:,.0f} € + Honorarios: {total_honorarios_base:,.0f} € + Tasas: {total_tasas_pagadas:,.0f} €)")
    else:
        st.caption(f"Ref: {datos_obra['codigo']} | Estado: **{est_exp}** | Presupuesto Ejecución: **{datos_obra['presupuesto_total']:,.0f} €**")

with col_head2:
    st.write("")
    cierre_row_obj = df_cierre.iloc[0] if not df_cierre.empty else None
    if rol == "Arquitecto":
        pdf_maestro = generar_expediente_maestro_pdf(datos_obra, df_honorarios, df_tramites, df_licit, df_cert, cierre_row_obj)
        st.download_button("📥 Descargar Expediente Maestro (PDF)", pdf_maestro, file_name=f"Expediente_Maestro_{datos_obra['codigo']}.pdf", mime="application/pdf", use_container_width=True)

if est_exp != "En Curso / Activo" and rol == "Arquitecto":
    st.warning(f"🔒 **EXPEDIENTE ARCHIVADO:** Este encargo se encuentra en estado *'{est_exp}'*. Las nuevas modificaciones están bloqueadas.")

# ==========================================
# ESTRUCTURA POR 5 FASES CRONOLÓGICAS
# ==========================================
tab_fase1, tab_fase2, tab_fase3, tab_fase4, tab_fase5 = st.tabs([
    "📐 FASE 1: Viabilidad y Anteproyecto",
    "🏛️ FASE 2: Licencias y Trámites",
    "⚖️ FASE 3: Licitación y Contratas",
    "🏗️ FASE 4: Ejecución y Dirección de Obra",
    "🏁 FASE 5: Cierre, Finiquito y Posventa"
])

# ---------------------------------------------------------
# FASE 1
# ---------------------------------------------------------
with tab_fase1:
    # ---------------------------------------------------------
    # 1.1 BUZÓN DE COMUNICACIONES RÁPIDAS (Exclusivo Cliente - Arquitecto)
    # ---------------------------------------------------------
    if rol in ["Arquitecto", "Cliente"]:
        # 1. Leemos los mensajes ANTES de dibujar la caja para saber si hay alertas
        df_buzon = pd.read_sql_query("SELECT * FROM buzon_cliente WHERE obra_id = ? ORDER BY id ASC", conn, params=(obra_id_activa,))
        
        # 2. Lógica de alerta: Si el último mensaje es del cliente y tú eres el arquitecto
        hay_aviso_rojo = False
        if not df_buzon.empty and rol == "Arquitecto":
            ultimo_emisor = df_buzon.iloc[-1]["emisor"]
            if ultimo_emisor != "Arquitecto":
                hay_aviso_rojo = True
                
        # 3. Dibujamos una alerta roja súper visible si hay aviso
        if hay_aviso_rojo:
            st.error("🚨 **TIENES UN NUEVO MENSAJE DEL CLIENTE POR LEER**")
            titulo_buzon = "🚨 💬 BANDEJA DE MENSAJES (NUEVO AVISO)"
        else:
            titulo_buzon = "💬 Bandeja de Mensajes y Avisos del Expediente"

        # 4. Creamos el Expander (Cerrado por defecto con expanded=False)
        with st.expander(titulo_buzon, expanded=False):
            
            # --- HISTORIAL EN CAJA CON SCROLL ---
            st.markdown("##### 📥 Historial de Conversación")
            chat_container = st.container(height=250)
            
            with chat_container:
                if not df_buzon.empty:
                    for _, r_msg in df_buzon.iterrows():
                        c_msg, c_del = st.columns([15, 1])
                        with c_msg:
                            if r_msg["emisor"] == "Arquitecto":
                                st.info(f"📐 **Dirección Facultativa** ({r_msg['fecha']}):\n\n{r_msg['mensaje']}")
                            else:
                                st.success(f"🤝 **Promotor / Cliente** ({r_msg['fecha']}):\n\n{r_msg['mensaje']}")
                        with c_del:
                            if rol == "Arquitecto":
                                if st.button("🗑️", key=f"del_msg_{r_msg['id']}", help="Eliminar"):
                                    cursor.execute("DELETE FROM buzon_cliente WHERE id = ?", (r_msg['id'],))
                                    conn.commit()
                                    st.rerun()
                else:
                    st.caption("No hay mensajes registrados en este expediente.")
            
            st.write("")
            
            # --- ZONA DE ESCRITURA Y BOTONES COMPACTOS ---
            with st.form("form_nuevo_mensaje", clear_on_submit=True):
                nuevo_msg = st.text_area("Nuevo mensaje oficial para el cliente:", height=100)
                enviado = st.form_submit_button("📤 Guardar Mensaje en Plataforma")
                
                if enviado and nuevo_msg.strip() != "":
                    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
                    cursor.execute("INSERT INTO buzon_cliente (obra_id, fecha, emisor, mensaje) VALUES (?, ?, ?, ?)", 
                                   (obra_id_activa, fecha_hoy, rol, nuevo_msg))
                    conn.commit()
                    st.rerun()

            # --- AVISOS EXTERNOS (Elegantes y pequeños) ---
            if rol == "Arquitecto":
                import urllib.parse
                mensaje_base = f"Hola, he subido una nueva actualización al portal del proyecto '{datos_obra['nombre']}'. Por favor, entra con tu usuario para revisarlo y confirmarlo."
                msg_codificado = urllib.parse.quote(mensaje_base)
                
                st.caption("🔔 **Notificar actualización al cliente:**")
                col_wa, col_mail, col_vacia = st.columns([1, 1, 4])
                with col_wa:
                    st.markdown(f'<a href="https://wa.me/?text={msg_codificado}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:5px; background-color:#1E293B; color:#25D366; border:1px solid #2d2d2d; border-radius:4px; font-weight:bold; cursor:pointer; font-size:13px;">📱 WhatsApp</button></a>', unsafe_allow_html=True)
                with col_mail:
                    st.markdown(f'<a href="mailto:?subject=Actualización Proyecto {datos_obra["codigo"]}&body={msg_codificado}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:5px; background-color:#1E293B; color:#D44638; border:1px solid #2d2d2d; border-radius:4px; font-weight:bold; cursor:pointer; font-size:13px;">✉️ Email</button></a>', unsafe_allow_html=True)
                st.write("")

    
    st.markdown("### 📐 Fase 1: Viabilidad, Anteproyecto y Honorarios")
    if rol == "Arquitecto":
        with st.expander("🤝 1.1 Primer Encuentro y Estudio de Viabilidad", expanded=False):
            st.info("Registra el cobro de la primera visita al terreno o vivienda (Provisión de fondos) para asegurar tu tiempo.")
            cursor.execute("SELECT id, base_imponible, iva, retencion_irpf FROM honorarios WHERE obra_id = ? AND fase = '00. Visita Inicial y Viabilidad'", (obra_id_activa,))
            visita_existente = cursor.fetchone()
            valor_visita_actual = float(visita_existente[1]) if visita_existente else 150.0
            val_irpf_previo = 0.0
            if visita_existente and float(visita_existente[1]) > 0:
                val_irpf_previo = round((float(visita_existente[3]) / float(visita_existente[1])) * 100, 1)

            with st.form("form_viabilidad"):
                col_v1, col_v2, col_v3 = st.columns(3)
                with col_v1: coste_visita = st.number_input("Coste Primera Visita / Viabilidad (€):", min_value=0.0, step=50.0, value=valor_visita_actual)
                with col_v2: pct_iva_visita = st.selectbox("% IVA Visita:", [21, 10, 0], index=0)
                with col_v3: pct_irpf_visita = st.number_input("% Retención IRPF Visita:", min_value=0.0, max_value=35.0, value=float(val_irpf_previo), step=1.0)
                descontar_luego = st.checkbox("Deducible de los honorarios finales si se firma el contrato", value=True)
                if st.form_submit_button("Registrar / Actualizar Cobro Inicial") and est_exp == "En Curso / Activo":
                    iva = round(coste_visita * (pct_iva_visita / 100.0), 2)
                    irpf = round(coste_visita * (pct_irpf_visita / 100.0), 2)
                    total = round(coste_visita + iva - irpf, 2)
                    if visita_existente:
                        cursor.execute("UPDATE honorarios SET base_imponible = ?, iva = ?, retencion_irpf = ?, total_a_cobrar = ? WHERE id = ?", (coste_visita, iva, irpf, total, visita_existente[0]))
                    else:
                        cursor.execute("INSERT INTO honorarios (obra_id, fase, porcentaje, base_imponible, iva, retencion_irpf, total_a_cobrar, estado, fecha_emision, fecha_cobro) VALUES (?, ?, 0.0, ?, ?, ?, ?, 'Cobrado', ?, ?)", (obra_id_activa, "00. Visita Inicial y Viabilidad", coste_visita, iva, irpf, total, str(date.today()), str(date.today())))
                    conn.commit()
                    st.rerun()

    if rol in ["Arquitecto", "Cliente"]:
        with st.expander("🖼️ 1.2 Presentación de Anteproyecto (Visor Seguro)", expanded=False):
            if rol == "Arquitecto":
                with st.form("form_anteproyecto"):
                    titulo_ant = st.text_input("Título de la Propuesta (Ej: Opción 1 - Espacios Abiertos):")
                    archivo_ant = st.file_uploader("Adjuntar Propuesta (PDF, JPG, PNG):", type=["pdf", "jpg", "jpeg", "png"])
                    if st.form_submit_button("Subir al Visor") and est_exp == "En Curso / Activo":
                        if archivo_ant and titulo_ant:
                            nombre_ant = f"ANTEPROY_{datos_obra['codigo']}_{archivo_ant.name}".replace(" ", "_")
                            ruta_ant = os.path.join(UPLOAD_DIR, nombre_ant)
                            with open(ruta_ant, "wb") as f_out: f_out.write(archivo_ant.getbuffer())
                            cursor.execute("INSERT INTO anteproyectos (obra_id, titulo, archivo_path, fecha) VALUES (?, ?, ?, ?)", (obra_id_activa, titulo_ant, ruta_ant, str(date.today())))
                            conn.commit()
                            st.rerun()

            if not df_anteproyectos.empty:
                st.markdown("#### Propuestas Presentadas")
                if rol == "Arquitecto" and est_exp == "En Curso / Activo":
                    with st.expander("⚙️ Eliminar Anteproyecto"):
                        opc_ant = {f"ID {r['id']} - {r['titulo']}": r['id'] for _, r in df_anteproyectos.iterrows()}
                        sel_ant = st.selectbox("Seleccionar para eliminar:", list(opc_ant.keys()), key="sel_del_ant")
                        id_ant_sel = opc_ant[sel_ant]
                        if st.button("🗑️ Eliminar Definitivamente", key="btn_del_ant"):
                            ruta_arch = df_anteproyectos[df_anteproyectos["id"] == id_ant_sel].iloc[0]["archivo_path"]
                            if os.path.exists(ruta_arch):
                                os.remove(ruta_arch) # Borra el archivo físico
                            cursor.execute("DELETE FROM anteproyectos WHERE id = ?", (id_ant_sel,))
                            conn.commit()
                            st.success("Anteproyecto eliminado.")
                            st.rerun()
                for _, r_a in df_anteproyectos.iterrows():
                    st.write(f"**{r_a['titulo']}** ({r_a['fecha']})")
                    ruta_arch = r_a["archivo_path"]
                    if os.path.exists(ruta_arch):
                        if ruta_arch.lower().endswith(".pdf"):
                            try:
                                with open(ruta_arch, "rb") as f_pdf:
                                    b64_pdf = base64.b64encode(f_pdf.read()).decode('utf-8')
                                pdf_display = f'<embed src="data:application/pdf;base64,{b64_pdf}#toolbar=0&navpanes=0&scrollbar=0" type="application/pdf" width="100%" height="600px" />'
                                st.markdown(pdf_display, unsafe_allow_html=True)
                            except Exception: st.error("Error al renderizar el archivo PDF.")
                        else:
                            st.image(ruta_arch, width="stretch")
                    st.divider()

    if rol == "Arquitecto":
        with st.expander("🛠️ 1.3 Archivos y Datos Técnicos (Geotecnia y Estructuras)", expanded=False):
            ing_row = df_ing.iloc[0] if not df_ing.empty else None
            val_sigma = float(ing_row["tension_adm"]) if (ing_row is not None and pd.notna(ing_row["tension_adm"])) else 2.0
            val_freatico = float(ing_row["nivel_freatico"]) if (ing_row is not None and pd.notna(ing_row["nivel_freatico"])) else -1.0
            val_coste_geo = float(ing_row["coste_geotecnico"]) if (ing_row is not None and pd.notna(ing_row["coste_geotecnico"])) else 950.0
            val_obs_geo = str(ing_row["observaciones"]) if (ing_row is not None and pd.notna(ing_row["observaciones"])) else ""
            val_coste_est = float(ing_row["coste_estructuras"]) if (ing_row is not None and pd.notna(ing_row["coste_estructuras"])) else 1500.0

            with st.form("form_estudios_tecnicos"):
                col_geo, col_est = st.columns(2)
                with col_geo:
                    st.markdown("#### 🌍 Estudio Geotécnico")
                    tipo_terreno = st.selectbox("Clasificación del Terreno:", ["Tipo I: Roca", "Tipo II: Arenas densas", "Tipo III: Arcillas semiduras", "Tipo IV: Rellenos"], index=0)
                    sigma_adm = st.number_input("Tensión Admisible (kg/cm²):", min_value=0.1, value=val_sigma, step=0.1)
                    nivel_freatico = st.number_input("Nivel Freático (m, -1 si no hay):", value=val_freatico, step=0.5)
                    coste_geo = st.number_input("Coste Estudio Geotécnico (€):", min_value=0.0, step=50.0, value=val_coste_geo)
                    obs_geo = st.text_area("Conclusiones Geotécnicas:", value=val_obs_geo)
                    file_geo = st.file_uploader("Adjuntar PDF Geotécnico:", type=["pdf"])

                with col_est:
                    st.markdown("#### 🏗️ Cálculo de Estructuras")
                    realizado_por = st.selectbox("Realizado por:", ["Estudio Propio (Interno)", "Ingeniería Externa", "Constructora"], index=0)
                    coste_est = st.number_input("Coste Cálculo Estructural (€):", min_value=0.0, step=100.0, value=val_coste_est)
                    file_est = st.file_uploader("Adjuntar PDF Estructuras:", type=["pdf"])

                if st.form_submit_button("💾 Guardar Datos y Archivos Técnicos") and est_exp == "En Curso / Activo":
                    ruta_geo = ing_row["archivo_geo"] if (ing_row is not None and pd.notna(ing_row["archivo_geo"])) else ""
                    if file_geo:
                        ruta_geo = os.path.join(UPLOAD_DIR, f"GEO_{datos_obra['codigo']}_{file_geo.name}".replace(" ", "_"))
                        with open(ruta_geo, "wb") as f: f.write(file_geo.getbuffer())
                    ruta_est = ing_row["archivo_est"] if (ing_row is not None and pd.notna(ing_row["archivo_est"])) else ""
                    if file_est:
                        ruta_est = os.path.join(UPLOAD_DIR, f"EST_{datos_obra['codigo']}_{file_est.name}".replace(" ", "_"))
                        with open(ruta_est, "wb") as f: f.write(file_est.getbuffer())

                    if ing_row is None:
                        cursor.execute("INSERT INTO ingenieria_datos (obra_id, tipo_terreno, tension_adm, nivel_freatico, sismicidad, observaciones, coste_geotecnico, archivo_geo, realizado_por_est, coste_estructuras, archivo_est) VALUES (?, ?, ?, ?, 'Baja', ?, ?, ?, ?, ?, ?)", (obra_id_activa, tipo_terreno, sigma_adm, nivel_freatico, obs_geo, coste_geo, ruta_geo, realizado_por, coste_est, ruta_est))
                    else:
                        cursor.execute("UPDATE ingenieria_datos SET tipo_terreno=?, tension_adm=?, nivel_freatico=?, observaciones=?, coste_geotecnico=?, archivo_geo=?, realizado_por_est=?, coste_estructuras=?, archivo_est=? WHERE obra_id=?", (tipo_terreno, sigma_adm, nivel_freatico, obs_geo, coste_geo, ruta_geo, realizado_por, coste_est, ruta_est, obra_id_activa))
                    conn.commit()
                    st.rerun()

            if ing_row is not None:
                st.markdown("---")
                st.markdown("##### 📄 Archivos e Informes Técnicos")
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    if pd.notna(ing_row["archivo_geo"]) and ing_row["archivo_geo"] and os.path.exists(ing_row["archivo_geo"]):
                        with open(ing_row["archivo_geo"], "rb") as f: st.download_button("⬇️ Descargar PDF Geotécnico", f, file_name=os.path.basename(ing_row["archivo_geo"]), key="dl_geo")
                with col_f2:
                    if pd.notna(ing_row["archivo_est"]) and ing_row["archivo_est"] and os.path.exists(ing_row["archivo_est"]):
                        with open(ing_row["archivo_est"], "rb") as f: st.download_button("⬇️ Descargar PDF Estructuras", f, file_name=os.path.basename(ing_row["archivo_est"]), key="dl_est")
                with col_f3:
                    pdf_tecnico = generar_informe_tecnico_pdf(datos_obra, ing_row)
                    st.download_button(label="📄 Generar Memoria Técnica (PDF)", data=pdf_tecnico, file_name=f"Memoria_Tecnica_{datos_obra['codigo']}.pdf", mime="application/pdf")

        # 1.4 HONORARIOS
        st.markdown("### 💰 1.4 Honorarios y Propuesta Comercial")
        if not df_honorarios.empty:
            total_hon_base = df_honorarios["base_imponible"].sum()
            cobrado_base = df_honorarios[df_honorarios["estado"] == "Cobrado"]["base_imponible"].sum()
            pendiente_cobro = total_hon_base - cobrado_base
            cobrado_total_facturas = df_honorarios[df_honorarios["estado"] == "Cobrado"]["total_a_cobrar"].sum()

            h1, h2, h3 = st.columns(3)
            h1.metric("Honorarios Totales (Base)", f"{total_hon_base:,.2f} €")
            h2.metric("Total Cobrado (c/Impuestos)", f"{cobrado_total_facturas:,.2f} €")
            h3.metric("Pendiente de Cobro", f"{pendiente_cobro:,.2f} €", delta=f"{-pendiente_cobro:,.2f} €")
            
            st.divider()

        col_h_gen, col_h_man = st.columns(2)
        with col_h_gen:
            if est_exp == "En Curso / Activo":
                with st.expander("⚡ Desglose Modular de Fases de Proyecto", expanded=df_honorarios.empty):
                    cursor.execute("SELECT base_imponible FROM honorarios WHERE obra_id = ? AND fase = '00. Visita Inicial y Viabilidad'", (obra_id_activa,))
                    r_vis = cursor.fetchone()
                    anticipo_visita = float(r_vis[0]) if r_vis else 0.0

                    with st.form("form_auto_honorarios"):
                        hon_total_input = st.number_input("Base Estimada Proyecto Completo (€):", min_value=500.0, step=500.0, value=float(hon_guardados))
                        c_tax1, c_tax2 = st.columns(2)
                        with c_tax1: pct_iva = st.selectbox("% IVA:", [21, 10, 0], index=0)
                        with c_tax2: pct_irpf = st.number_input("% Retención IRPF:", min_value=0.0, max_value=35.0, value=0.0, step=1.0)

                        st.markdown("**Selecciona las fases a contratar ahora:**")
                        inc_f1 = st.checkbox("01. Estudios Previos y Anteproyecto (15%)", value=True)
                        inc_f2 = st.checkbox("02. Proyecto Básico - Licencia (20%)", value=True)
                        inc_f3 = st.checkbox("03. Proyecto Ejecutivo y Arquitectura (30%)", value=False)
                        inc_f4 = st.checkbox("04. Dirección de Obra y Liquidación Final (35%)", value=False)

                        st.markdown("**Servicios Adicionales**")
                        def_coste_geo = float(ing_row["coste_geotecnico"]) if (ing_row is not None and pd.notna(ing_row["coste_geotecnico"])) else 950.0
                        def_coste_est = float(ing_row["coste_estructuras"]) if (ing_row is not None and pd.notna(ing_row["coste_estructuras"])) else 1500.0
                        inc_geo = st.checkbox("05. Gestión Estudio Geotécnico", value=False)
                        coste_geo_hon = st.number_input("Cobro Estudio Geotécnico (€):", value=def_coste_geo) if inc_geo else 0.0
                        inc_est = st.checkbox("06. Cálculo de Estructuras", value=False)
                        coste_est_hon = st.number_input("Cobro Cálculo Estructural (€):", value=def_coste_est) if inc_est else 0.0

                        if st.form_submit_button("🚀 Generar / Actualizar Fases Seleccionadas"):
                            cursor.execute("UPDATE obras SET honorarios_base = ? WHERE id = ?", (hon_total_input, obra_id_activa))
                            cursor.execute("DELETE FROM honorarios WHERE obra_id = ? AND (fase LIKE '01.%' OR fase LIKE '02.%' OR fase LIKE '03.%' OR fase LIKE '04.%' OR fase LIKE '05.%' OR fase LIKE '06.%')", (obra_id_activa,))
                            fases_a_incluir = []
                            if inc_f1: fases_a_incluir.append(("01. Estudios Previos y Anteproyecto", 15.0, max(0.0, (hon_total_input * 0.15) - anticipo_visita)))
                            if inc_f2: fases_a_incluir.append(("02. Proyecto Básico (Solicitud Licencia)", 20.0, hon_total_input * 0.20))
                            if inc_f3: fases_a_incluir.append(("03. Proyecto Ejecutivo y Arquitectura", 30.0, hon_total_input * 0.30))
                            if inc_f4: fases_a_incluir.append(("04. Dirección de Obra y Liquidación Final", 35.0, hon_total_input * 0.35))
                            if inc_geo: fases_a_incluir.append(("05. Gestión Estudio Geotécnico", 0.0, coste_geo_hon))
                            if inc_est: fases_a_incluir.append(("06. Cálculo de Estructuras", 0.0, coste_est_hon))

                            for nom_fase, pct_fase, base_fase in fases_a_incluir:
                                iva_fase = round(base_fase * (pct_iva / 100.0), 2)
                                irpf_fase = round(base_fase * (pct_irpf / 100.0), 2)
                                total_factura = round(base_fase + iva_fase - irpf_fase, 2)
                                cursor.execute("INSERT INTO honorarios (obra_id, fase, porcentaje, base_imponible, iva, retencion_irpf, total_a_cobrar, estado, fecha_emision, fecha_cobro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, nom_fase, pct_fase, base_fase, iva_fase, irpf_fase, total_factura, "Pendiente", "-", "-"))
                            conn.commit()
                            st.rerun()

        with col_h_man:
            if not df_honorarios.empty:
                st.markdown("#### 📋 Cuadro de Minutas")
                st.dataframe(df_honorarios[["id", "fase", "base_imponible", "iva", "retencion_irpf", "total_a_cobrar", "estado", "fecha_cobro"]], width="stretch")
                if est_exp == "En Curso / Activo":
                    st.markdown("#### 💳 Registrar Cobro o Eliminar")
                    opciones_h = {f"ID {r['id']} - {r['fase']} ({r['total_a_cobrar']:,.2f} €)": r['id'] for _, r in df_honorarios.iterrows()}
                    sel_h_txt = st.selectbox("Selecciona Fase:", list(opciones_h.keys()), key="sb_sel_fase_cobro")
                    id_h_sel = opciones_h[sel_h_txt]
                    r_sel_actual = df_honorarios[df_honorarios["id"] == id_h_sel].iloc[0]
                    
                    with st.form("form_estado_cobro", clear_on_submit=False):
                        nuevo_estado_hon = st.selectbox("Estado de la Fase:", ["Pendiente", "Factura Emitida", "Cobrado"], index=["Pendiente", "Factura Emitida", "Cobrado"].index(r_sel_actual["estado"]) if r_sel_actual["estado"] in ["Pendiente", "Factura Emitida", "Cobrado"] else 0, key="sb_est_fase_cobro")
                        f_cobro = st.date_input("Fecha de Cobro:", value=date.today(), key="dt_fase_cobro")
                        if st.form_submit_button("💾 Actualizar Cobro", use_container_width=True):
                            txt_fcobro = str(f_cobro) if nuevo_estado_hon == "Cobrado" else "-"
                            cursor.execute("UPDATE honorarios SET estado = ?, fecha_cobro = ? WHERE id = ?", (nuevo_estado_hon, txt_fcobro, id_h_sel))
                            conn.commit()
                            st.rerun()
                    if st.button("🗑️ Eliminar Fase Seleccionada", type="primary", use_container_width=True, key="btn_del_fase"):
                        cursor.execute("DELETE FROM honorarios WHERE id = ?", (id_h_sel,))
                        conn.commit()
                        st.rerun()

# ---------------------------------------------------------
# FASE 2: GESTIÓN MUNICIPAL Y VISADOS
# ---------------------------------------------------------
with tab_fase2:
    st.markdown("### 🏛️ Fase 2: Licencias, Visados y Requerimientos Administrativos")
    if not df_tramites.empty:
        concedidas = len(df_tramites[df_tramites["estado"] == "Concedida / Favorable"])
        en_tramite = len(df_tramites[df_tramites["estado"].isin(["Presentado / En Trámite", "Requerimiento Pendiente"])])
        t1, t2, t3 = st.columns(3)
        t1.metric("Trámites en Curso", f"{en_tramite}")
        t2.metric("Licencias Concedidas", f"{concedidas}")
        t3.metric("Total Tasas / ICIO Pagadas", f"{total_tasas_pagadas:,.2f} €")
        st.divider()

    col_t_form, col_t_edit = st.columns(2)
    with col_t_form:
        if est_exp == "En Curso / Activo" and rol == "Arquitecto":
            with st.expander("➕ Registrar Nuevo Trámite / Licencia"):
                with st.form("form_nuevo_tramite", clear_on_submit=True):
                    organismo = st.selectbox("Organismo / Entidad:", ["Ayuntamiento (Licencia de Obras)", "Colegio de Arquitectos (Visado Colegial)", "Compañía Eléctrica (Acometida / Endesa / Iberdrola)", "Compañía de Agua (Acometida / Saneamiento)", "Dirección Gral. de Carreteras / Costas", "Comisión de Patrimonio Histórico", "Agencia de Residuos"])
                    tipo_tramite = st.selectbox("Tipo de Expediente:", ["Licencia de Obra Mayor", "Comunicación Previa / Obra Menor", "Visado Proyecto Básico", "Visado Proyecto Ejecutivo y CFO", "Consulta Urbanística Previa", "Solicitud de Acometida Definitiva", "Licencia de Primera Ocupación (LPO)"])
                    num_exp = st.text_input("Nº de Expediente / Referencia:", placeholder="Ej: EXP-2026/0412")
                    f_solicitud = st.date_input("Fecha de Presentación:", value=date.today())
                    tiene_limite = st.checkbox("¿Tiene fecha límite de respuesta (Requerimiento)?")
                    f_limite = st.date_input("Fecha Límite:", value=date.today() + timedelta(days=15)) if tiene_limite else "-"
                    tasas = st.number_input("Tasas / Impuestos Abonados (€):", min_value=0.0, step=50.0, value=0.0)
                    estado_tr = st.selectbox("Estado:", ["Presentado / En Trámite", "Requerimiento Pendiente", "Concedida / Favorable", "Denegada / Desestimada"])
                    obs_tr = st.text_area("Observaciones o Requerimientos Técnicos:")
                    if st.form_submit_button("Guardar Trámite"):
                        cursor.execute("INSERT INTO tramites (obra_id, organismo, tipo_tramite, num_expediente, fecha_solicitud, fecha_limite, tasas_euros, estado, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, organismo, tipo_tramite, num_exp, str(f_solicitud), str(f_limite), tasas, estado_tr, obs_tr))
                        conn.commit()
                        st.rerun()

    with col_t_edit:
        if not df_tramites.empty and rol == "Arquitecto":
            with st.expander("⚙️ Actualizar o Eliminar Expediente"):
                opciones_tr = {f"ID {r['id']} - {r['organismo'][:20]} ({r['num_expediente']})": r['id'] for _, r in df_tramites.iterrows()}
                sel_tr_txt = st.selectbox("Selecciona Expediente:", list(opciones_tr.keys()))
                id_tr_sel = opciones_tr[sel_tr_txt]
                r_tr_act = df_tramites[df_tramites["id"] == id_tr_sel].iloc[0]
                with st.form("form_edit_tramite"):
                    nuevo_est_tr = st.selectbox("Estado Actual:", ["Presentado / En Trámite", "Requerimiento Pendiente", "Concedida / Favorable", "Denegada / Desestimada"], index=["Presentado / En Trámite", "Requerimiento Pendiente", "Concedida / Favorable", "Denegada / Desestimada"].index(r_tr_act["estado"]))
                    nueva_obs_tr = st.text_area("Observaciones:", value=r_tr_act["observaciones"])
                    cb1, cb2 = st.columns(2)
                    if cb1.form_submit_button("💾 Guardar"):
                        cursor.execute("UPDATE tramites SET estado = ?, observaciones = ? WHERE id = ?", (nuevo_est_tr, nueva_obs_tr, id_tr_sel))
                        conn.commit()
                        st.rerun()
                    if est_exp == "En Curso / Activo" and cb2.form_submit_button("🗑️ Eliminar"):
                        cursor.execute("DELETE FROM tramites WHERE id = ?", (id_tr_sel,))
                        conn.commit()
                        st.rerun()

    if not df_tramites.empty:
        st.markdown("#### 📑 Historial Administrativo")
        st.dataframe(df_tramites[["id", "organismo", "tipo_tramite", "num_expediente", "fecha_solicitud", "fecha_limite", "tasas_euros", "estado", "observaciones"]], width="stretch")

# ---------------------------------------------------------
# FASE 3: CONTRATACIÓN Y LICITACIÓN
# ---------------------------------------------------------
with tab_fase3:
    if rol != "Arquitecto":
        st.info("🔒 Las comparativas de licitación son información confidencial de la Dirección Facultativa.")
    else:
        st.markdown("### ⚖️ Fase 3: Cuadro Comparativo de Ofertas y Adjudicación")
        if not df_licit.empty:
            total_estimado_lic = df_licit["presupuesto_estimado"].sum()
            total_adjudicado = df_licit[df_licit["estado"] == "Adjudicado"]["monto_adjudicado"].sum()
            ahorro_baja = total_estimado_lic - total_adjudicado
            l1, l2, l3 = st.columns(3)
            l1.metric("PEM Estimado de Licitación", f"{total_estimado_lic:,.2f} €")
            l2.metric("Total Contratado / Adjudicado", f"{total_adjudicado:,.2f} €")
            l3.metric("Baja / Ahorro Obtenido", f"{ahorro_baja:,.2f} €", delta=ahorro_baja)
            st.divider()

        col_lic_c, col_lic_adj = st.columns(2)
        with col_lic_c:
            if est_exp == "En Curso / Activo":
                with st.expander("➕ Añadir Paquete de Licitación"):
                    with st.form("form_nueva_licitacion", clear_on_submit=True):
                        capitulo_lic = st.selectbox("Capítulo o Paquete:", ["00. Obra Completa (Contrata Principal)", "01. Demoliciones y Mov. Tierras", "02. Estructura y Cimentación", "03. Fachadas y Cubiertas", "04. Instalación Eléctrica", "05. Fontanería y Clima", "06. Carpintería Exterior", "07. Carpintería Interior", "08. Pavimentos y Pintura"])
                        pem_estimado = st.number_input("Presupuesto PEM Estimado (€):", min_value=0.0, step=1000.0, value=35000.0)
                        c_ea1, c_ea2 = st.columns(2)
                        with c_ea1: emp_a = st.text_input("Empresa A:", value="Constructora A")
                        with c_ea2: ofert_a = st.number_input("Oferta A (€):", min_value=0.0, step=500.0, value=36000.0)
                        c_eb1, c_eb2 = st.columns(2)
                        with c_eb1: emp_b = st.text_input("Empresa B:", value="Constructora B")
                        with c_eb2: ofert_b = st.number_input("Oferta B (€):", min_value=0.0, step=500.0, value=33500.0)
                        c_ec1, c_ec2 = st.columns(2)
                        with c_ec1: emp_c = st.text_input("Empresa C:", value="Constructora C")
                        with c_ec2: ofert_c = st.number_input("Oferta C (€):", min_value=0.0, step=500.0, value=34800.0)
                        if st.form_submit_button("Guardar Comparativa"):
                            cursor.execute("INSERT INTO licitaciones (obra_id, capitulo, presupuesto_estimado, empresa_a, oferta_a, empresa_b, oferta_b, empresa_c, oferta_c, empresa_adjudicada, monto_adjudicado, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, capitulo_lic, pem_estimado, emp_a, ofert_a, emp_b, ofert_b, emp_c, oferta_c, "-", 0.0, "En Estudio"))
                            conn.commit()
                            st.rerun()

        with col_lic_adj:
            if not df_licit.empty:
                with st.expander("🏆 Adjudicar Oferta Ganadora"):
                    opciones_lic = {f"ID {r['id']} - {r['capitulo']} (Est: {r['presupuesto_estimado']:,.0f} €)": r['id'] for _, r in df_licit.iterrows()}
                    sel_lic_txt = st.selectbox("Selecciona Paquete:", list(opciones_lic.keys()))
                    id_lic_sel = opciones_lic[sel_lic_txt]
                    r_lic_act = df_licit[df_licit["id"] == id_lic_sel].iloc[0]

                    desv_a = ((r_lic_act['oferta_a'] - r_lic_act['presupuesto_estimado']) / r_lic_act['presupuesto_estimado'] * 100) if r_lic_act['presupuesto_estimado'] > 0 else 0
                    desv_b = ((r_lic_act['oferta_b'] - r_lic_act['presupuesto_estimado']) / r_lic_act['presupuesto_estimado'] * 100) if r_lic_act['presupuesto_estimado'] > 0 else 0
                    desv_c = ((r_lic_act['oferta_c'] - r_lic_act['presupuesto_estimado']) / r_lic_act['presupuesto_estimado'] * 100) if r_lic_act['presupuesto_estimado'] > 0 else 0

                    st.info(f"🔹 **{r_lic_act['empresa_a']}**: {r_lic_act['oferta_a']:,.2f} € ({desv_a:+.1f}%)\n\n🔹 **{r_lic_act['empresa_b']}**: {r_lic_act['oferta_b']:,.2f} € ({desv_b:+.1f}%)\n\n🔹 **{r_lic_act['empresa_c']}**: {r_lic_act['oferta_c']:,.2f} € ({desv_c:+.1f}%)")

                    with st.form("form_adjudicar_lic"):
                        opc_ganador = [f"{r_lic_act['empresa_a']} - {r_lic_act['oferta_a']:,.2f} €", f"{r_lic_act['empresa_b']} - {r_lic_act['oferta_b']:,.2f} €", f"{r_lic_act['empresa_c']} - {r_lic_act['oferta_c']:,.2f} €"]
                        ganador_sel = st.selectbox("Adjudicataria:", opc_ganador)
                        col_adj1, col_adj2 = st.columns(2)
                        if col_adj1.form_submit_button("✅ Adjudicar"):
                            emp_nom = ganador_sel.split(" - ")[0]
                            monto_ganador = float(ganador_sel.split(" - ")[1].replace(" €", "").replace(",", ""))
                            cursor.execute("UPDATE licitaciones SET empresa_adjudicada = ?, monto_adjudicado = ?, estado = 'Adjudicado' WHERE id = ?", (emp_nom, monto_ganador, id_lic_sel))
                            conn.commit()
                            st.rerun()
                        if est_exp == "En Curso / Activo" and col_adj2.form_submit_button("🗑️ Eliminar"):
                            cursor.execute("DELETE FROM licitaciones WHERE id = ?", (id_lic_sel,))
                            conn.commit()
                            st.rerun()

        if not df_licit.empty:
            st.markdown("#### 📋 Matriz de Licitaciones")
            st.dataframe(df_licit[["id", "capitulo", "presupuesto_estimado", "empresa_a", "oferta_a", "empresa_b", "oferta_b", "empresa_c", "oferta_c", "empresa_adjudicada", "monto_adjudicado", "estado"]], width="stretch")

# ---------------------------------------------------------
# FASE 4: DIRECCIÓN DE OBRA Y EJECUCIÓN MATERIAL
# ---------------------------------------------------------
with tab_fase4:
    st.markdown("### 🏗️ Fase 4: Dirección de Obra y Ejecución")
    subtab_gantt, subtab_cert, subtab_docs, subtab_ordenes = st.tabs(["📅 Cronograma y Curva S", "📑 Certificaciones Mensuales (5% Retención)", "📂 Planos y Entregas (CDE)", "📝 Libro de Órdenes y Fotografías"])

    # 4.1 Cronograma y Curva S
    with subtab_gantt:
        if not df_gantt.empty:
            g1, g2, g3, g4 = st.columns(4)
            g1.metric("Presupuesto Programado", f"{total_previsto:,.2f} €")
            g2.metric("🏗️ Avance Físico Global", f"{pct_fisico_global:.1f}%", f"{total_fisico_euros:,.2f} € ejecutados")
            g3.metric("💶 Avance Certificado Global", f"{pct_financiero_global:.1f}%", f"{total_cert_bruto:,.2f} € certificados")
            desfase = total_fisico_euros - total_cert_bruto
            g4.metric("Desfase Físico vs. Financiero", f"{desfase:,.2f} €", delta=desfase)
            st.divider()

            # --- MÓDULO DE ALERTAS Y AUTOCORRECCIÓN ---
        hoy = str(date.today())
        retrasadas = df_gantt[(df_gantt["fecha_fin"] < hoy) & (df_gantt["avance_porcentaje"] < 100)]
        
        desvio_presupuesto = abs(total_previsto - datos_obra["presupuesto_total"]) > 0.01

        if not retrasadas.empty or desvio_presupuesto:
            st.markdown("#### ⚠️ Alertas Críticas de Ejecución")
            if not retrasadas.empty:
                for _, r in retrasadas.iterrows():
                    st.error(f"🚨 **Retraso:** '{r['tarea']}' debió finalizar el {r['fecha_fin']} (Avance actual: {r['avance_porcentaje']}%).")
            
            if desvio_presupuesto:
                diferencia = total_previsto - datos_obra["presupuesto_total"]
                if diferencia > 0:
                    st.warning(f"⚠️ **Desvío:** El total programado supera el presupuesto en +{diferencia:,.2f} €.")
                else:
                    st.warning(f"⚠️ **Desvío:** Falta programar {-diferencia:,.2f} € para alcanzar el presupuesto base.")
                
                if st.button("🪄 Auto-Ajustar Partidas Proporcionalmente al Presupuesto Base"):
                    if total_previsto > 0:
                        factor_escala = datos_obra["presupuesto_total"] / total_previsto
                        cursor.execute("UPDATE cronograma SET coste_estimado = ROUND(coste_estimado * ?, 2) WHERE obra_id = ?", (factor_escala, obra_id_activa))
                        conn.commit()
                        st.rerun()
        # ------------------------------------------

        if est_exp == "En Curso / Activo" and rol == "Arquitecto":
            with st.expander("⚡ Certificar % de Avance Físico en Obra (Por Partida)"):
                if not df_gantt.empty:
                    opc_partidas = {f"[{r['etapa'][:18]}] {r['tarea']} (Avance: {r['avance_porcentaje']}%)": r['id'] for _, r in df_gantt.iterrows()}
                    sel_partida_txt = st.selectbox("Selecciona Partida:", list(opc_partidas.keys()))
                    id_partida_sel = opc_partidas[sel_partida_txt]
                    r_partida_act = df_gantt[df_gantt["id"] == id_partida_sel].iloc[0]
                    with st.form("form_avance_fisico"):
                        nuevo_av_fisico = st.slider("Nuevo % de Ejecución Real:", 0, 100, int(r_partida_act["avance_porcentaje"]))
                        if st.form_submit_button("Actualizar Avance"):
                            cursor.execute("UPDATE cronograma SET avance_porcentaje = ? WHERE id = ?", (nuevo_av_fisico, id_partida_sel))
                            conn.commit()
                            st.rerun()

            with st.expander("⚙️ Generador Automático de Cronograma", expanded=df_gantt.empty):
                with st.form("form_autoplan"):
                    c_auto1, c_auto2, c_auto3 = st.columns(3)
                    with c_auto1: tipo_obra = st.selectbox("Tipología:", ["Reforma Integral de Vivienda", "Obra Nueva Unifamiliar Aislada", "Adecuación de Local Comercial"])
                    with c_auto2: fecha_inicio_auto = st.date_input("Fecha Inicio:", value=date.today())
                    with c_auto3: meses_obra = st.number_input("Duración (Meses):", min_value=1, max_value=36, value=6)
                    if st.form_submit_button("🚀 Generar Cronograma Automático"):
                        cursor.execute("DELETE FROM cronograma WHERE obra_id = ?", (obra_id_activa,))
                        dias_totales = meses_obra * 30
                        presupuesto_base = datos_obra["presupuesto_total"]
                        matriz = [
                            ("01. Demoliciones y Mov. Tierras", "Demoliciones y desescombros", 0.00, 0.15, 0.08, "Demoliciones"),
                            ("04. Instalaciones", "Instalación eléctrica y fontanería", 0.12, 0.45, 0.28, "Instalaciones"),
                            ("03. Cerramientos y Cubierta", "Tabiquería Pladur y techos", 0.35, 0.65, 0.18, "Pladur"),
                            ("05. Acabados y Pintura", "Alicatados y solados", 0.55, 0.80, 0.22, "Solados"),
                            ("06. Carpinterías", "Carpinterías interiores y exteriores", 0.70, 0.92, 0.16, "Carpintería"),
                            ("05. Acabados y Pintura", "Pintura general y limpieza", 0.85, 1.00, 0.08, "Pintura")
                        ]
                        for etapa_m, tarea_m, pct_ini, pct_fin, pct_coste, resp_m in matriz:
                            f_ini_calc = fecha_inicio_auto + timedelta(days=int(dias_totales * pct_ini))
                            f_fin_calc = fecha_inicio_auto + timedelta(days=int(dias_totales * pct_fin))
                            coste_calc = round(presupuesto_base * pct_coste, 2)
                            cursor.execute("INSERT INTO cronograma (obra_id, etapa, tarea, fecha_inicio, fecha_fin, coste_estimado, avance_porcentaje, responsable) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, etapa_m, tarea_m, str(f_ini_calc), str(f_fin_calc), coste_calc, 0, resp_m))
                        conn.commit()
                        st.rerun()

            col_crear_gantt, col_editar_gantt = st.columns(2)
            with col_crear_gantt:
                with st.expander("➕ Añadir Partida Manual"):
                    with st.form("form_cronograma_manual", clear_on_submit=True):
                        etapas_disponibles = ["01. Demoliciones y Mov. Tierras", "02. Cimentación y Estructura", "03. Cerramientos y Cubierta", "04. Instalaciones", "05. Acabados y Pintura", "06. Carpinterías"]
                        etapa_man = st.selectbox("Capítulo / Etapa:", etapas_disponibles)
                        tarea_man = st.text_input("Descripción de la Partida:")
                        f_inicio_man = st.date_input("Fecha Inicio:", value=date.today())
                        f_fin_man = st.date_input("Fecha Fin:", value=date.today())
                        coste_man = st.number_input("Presupuesto Partida (€):", min_value=0.0, step=500.0, value=5000.0)
                        resp_man = st.text_input("Responsable:", value="Constructora Principal")
                        if st.form_submit_button("Añadir al Cronograma"):
                            if tarea_man.strip() != "" and f_fin_man >= f_inicio_man:
                                cursor.execute("INSERT INTO cronograma (obra_id, etapa, tarea, fecha_inicio, fecha_fin, coste_estimado, avance_porcentaje, responsable) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, etapa_man, tarea_man, str(f_inicio_man), str(f_fin_man), coste_man, 0, resp_man))
                                conn.commit()
                                st.rerun()

            with col_editar_gantt:
                with st.expander("✏️ Editar o Modificar Partida"):
                    if not df_gantt.empty:
                        opciones_edicion = {f"ID {row['id']} - {row['tarea']}": row['id'] for _, row in df_gantt.iterrows()}
                        seleccion_edit_txt = st.selectbox("Selecciona la partida a editar:", list(opciones_edicion.keys()))
                        id_seleccionado = opciones_edicion[seleccion_edit_txt]
                        fila_actual = df_gantt[df_gantt["id"] == id_seleccionado].iloc[0]
                        with st.form("form_editar_partida"):
                            etapas_lista = ["01. Demoliciones y Mov. Tierras", "02. Cimentación y Estructura", "03. Cerramientos y Cubierta", "04. Instalaciones", "05. Acabados y Pintura", "06. Carpinterías"]
                            idx_etapa = etapas_lista.index(fila_actual["etapa"]) if fila_actual["etapa"] in etapas_lista else 0
                            edit_etapa = st.selectbox("Capítulo / Etapa:", etapas_lista, index=idx_etapa)
                            edit_tarea = st.text_input("Descripción:", value=fila_actual["tarea"])
                            f_ini_dt = datetime.strptime(str(fila_actual["fecha_inicio"])[:10], "%Y-%m-%d").date()
                            f_fin_dt = datetime.strptime(str(fila_actual["fecha_fin"])[:10], "%Y-%m-%d").date()
                            edit_f_inicio = st.date_input("Fecha Inicio:", value=f_ini_dt)
                            edit_f_fin = st.date_input("Fecha Fin:", value=f_fin_dt)
                            edit_coste = st.number_input("Presupuesto (€):", value=float(fila_actual["coste_estimado"]), step=500.0)
                            edit_responsable = st.text_input("Responsable:", value=fila_actual["responsable"])
                            edit_avance = st.slider("% Avance:", 0, 100, int(fila_actual["avance_porcentaje"]))
                            if st.form_submit_button("Guardar Cambios"):
                                if edit_tarea.strip() != "" and edit_f_fin >= edit_f_inicio:
                                    cursor.execute("UPDATE cronograma SET etapa = ?, tarea = ?, fecha_inicio = ?, fecha_fin = ?, coste_estimado = ?, avance_porcentaje = ?, responsable = ? WHERE id = ?", (edit_etapa, edit_tarea, str(edit_f_inicio), str(edit_f_fin), edit_coste, edit_avance, edit_responsable, id_seleccionado))
                                    conn.commit()
                                    st.rerun()
                    if not df_gantt.empty:
                        if st.button("🗑️ Eliminar Partida Seleccionada", use_container_width=True, type="primary"):
                            cursor.execute("DELETE FROM cronograma WHERE id = ?", (id_seleccionado,))
                            conn.commit()
                            st.rerun()

        if not df_gantt.empty:
            df_gantt_plot = df_gantt.copy()
            df_gantt_plot["fecha_inicio_plot"] = pd.to_datetime(df_gantt_plot["fecha_inicio"])
            df_gantt_plot["fecha_fin_plot"] = pd.to_datetime(df_gantt_plot["fecha_fin"]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
            df_gantt_plot["Etiqueta_Avance"] = df_gantt_plot.apply(lambda r: f"{r['avance_porcentaje']}% ({(r['coste_estimado'] * r['avance_porcentaje'] / 100.0):,.0f} €)", axis=1)

            fig = px.timeline(df_gantt_plot, x_start="fecha_inicio_plot", x_end="fecha_fin_plot", y="tarea", color="etapa", text="Etiqueta_Avance", title="Diagrama de Gantt")
            fig.update_traces(textposition='inside', insidetextanchor='middle')
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, width="stretch")

            st.markdown("#### 📈 Curva S: Avance Previsto vs. Certificaciones Oficiales Emitidas")
            df_sorted_gantt = df_gantt_plot.sort_values(by="fecha_fin_plot")
            fechas_previstas = [df_gantt_plot["fecha_inicio_plot"].min()] + list(df_sorted_gantt["fecha_fin_plot"])
            acumulado_previsto = [0.0]
            acum = 0.0
            for val in df_sorted_gantt["coste_estimado"]:
                acum += val
                acumulado_previsto.append(acum)

            fig_curva_s = go.Figure()
            fig_curva_s.add_trace(go.Scatter(x=fechas_previstas, y=acumulado_previsto, mode='lines+markers', name='Planificación Prevista (Curva S)', line=dict(color='#3182CE', width=3, shape='spline'), marker=dict(size=6)))

            if not df_cert.empty:
                df_cert_plot = df_cert.copy()
                df_cert_plot["fecha_dt"] = pd.to_datetime(df_cert_plot["fecha_aprobacion"])
                df_cert_plot = df_cert_plot.sort_values(by="fecha_dt")
                fechas_cert = [df_gantt_plot["fecha_inicio_plot"].min()] + list(df_cert_plot["fecha_dt"])
                acumulado_cert = [0.0]
                acum_c = 0.0
                for val_c in df_cert_plot["importe_bruto"]:
                    acum_c += val_c
                    acumulado_cert.append(acum_c)
                fig_curva_s.add_trace(go.Scatter(x=fechas_cert, y=acumulado_cert, mode='lines+markers', name='Certificado Real Oficial', line=dict(color='#38A169', width=3.5), marker=dict(size=8, symbol='diamond')))

            fig_curva_s.add_hline(y=datos_obra["presupuesto_total"], line_dash="dash", line_color="#E53E3E", annotation_text=f"Presupuesto Contratado: {datos_obra['presupuesto_total']:,.0f} €", annotation_position="bottom right")
            fig_curva_s.update_layout(height=380, xaxis_title="Línea Temporal del Proyecto", yaxis_title="Euros Acumulados (€)", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_curva_s, use_container_width=True)
            st.dataframe(df_gantt[["id", "etapa", "tarea", "responsable", "fecha_inicio", "fecha_fin", "coste_estimado", "avance_porcentaje"]], use_container_width=True)

    # 4.2 Certificaciones
    with subtab_cert:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Certificado Acumulado", f"{total_cert_bruto:,.2f} €", f"{pct_financiero_global:.1f}%")
        c2.metric("Líquido Abonado", f"{total_abonado_liquido:,.2f} €")
        c3.metric("Fondo Retención 5%", f"{total_retenciones:,.2f} €")
        c4.metric("Ejecutado sin Certificar", f"{pendiente_certificar:,.2f} €", delta=pendiente_certificar)
        st.divider()

        col_cert_form, col_cert_edit = st.columns(2)
        with col_cert_form:
            if est_exp == "En Curso / Activo" and rol == "Arquitecto":
                with st.expander("➕ Emitir Certificación Mensual"):
                    with st.form("form_nueva_cert", clear_on_submit=True):
                        num_c = st.number_input("Nº Certificación:", min_value=1, value=len(df_cert)+1, step=1)
                        mes_c = st.text_input("Periodo / Mes:", value=datetime.now().strftime("%B %Y").capitalize())
                        bruto_c = st.number_input("Importe Bruto a Certificar (€):", min_value=0.0, step=500.0, value=float(pendiente_certificar))
                        pct_ret = st.selectbox("% Retención de Garantía:", [5.0, 0.0, 10.0], index=0)
                        obs_c = st.text_area("Observaciones de la Dirección de Obra:")
                        if st.form_submit_button("Emitir Acta"):
                            ret_calc = round(bruto_c * (pct_ret / 100.0), 2)
                            liq_calc = round(bruto_c - ret_calc, 2)
                            iva_calc = round(liq_calc * 0.21, 2)
                            tot_fact = round(liq_calc + iva_calc, 2)
                            cursor.execute("INSERT INTO certificaciones (obra_id, num_certificacion, mes_ano, importe_bruto, retencion_5pct, liquido_pagar, iva_21, total_factura, estado, fecha_aprobacion, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, num_c, mes_c, bruto_c, ret_calc, liq_calc, iva_calc, tot_fact, "Aprobada DF (Pendiente Pago)", datetime.now().strftime("%Y-%m-%d"), obs_c))
                            conn.commit()
                            st.rerun()

        with col_cert_edit:
            if not df_cert.empty and rol == "Arquitecto":
                with st.expander("⚙️ Modificar Estado / Eliminar"):
                    opc_cert = {f"Cert #{r['num_certificacion']} - {r['mes_ano']} (Líquido: {r['liquido_pagar']:,.2f} €)": r['id'] for _, r in df_cert.iterrows()}
                    sel_cert_txt = st.selectbox("Selecciona Certificación:", list(opc_cert.keys()))
                    id_cert_sel = opc_cert[sel_cert_txt]
                    r_cert_act = df_cert[df_cert["id"] == id_cert_sel].iloc[0]
                    with st.form("form_edit_cert"):
                        nuevo_est_cert = st.selectbox("Estado:", ["Aprobada DF (Pendiente Pago)", "Abonada / Pagada", "Retenida por Defectos / No Conforme"], index=["Aprobada DF (Pendiente Pago)", "Abonada / Pagada", "Retenida por Defectos / No Conforme"].index(r_cert_act["estado"]))
                        cb_c1, cb_c2 = st.columns(2)
                        if cb_c1.form_submit_button("💾 Guardar"):
                            cursor.execute("UPDATE certificaciones SET estado = ? WHERE id = ?", (nuevo_est_cert, id_cert_sel))
                            conn.commit()
                            st.rerun()
                        if est_exp == "En Curso / Activo" and cb_c2.form_submit_button("🗑️ Eliminar"):
                            cursor.execute("DELETE FROM certificaciones WHERE id = ?", (id_cert_sel,))
                            conn.commit()
                            st.rerun()

        if not df_cert.empty:
            st.dataframe(df_cert[["num_certificacion", "mes_ano", "importe_bruto", "retencion_5pct", "liquido_pagar", "iva_21", "total_factura", "estado", "fecha_aprobacion"]], width="stretch")

    # 4.3 Planos CDE
    with subtab_docs:
        col_d1, col_d2 = st.columns([1, 2])
        with col_d1:
            if est_exp == "En Curso / Activo" and rol == "Arquitecto":
                st.markdown("#### 📤 Registrar Entrega de Plano")
                with st.form("form_documentos", clear_on_submit=True):
                    tipo_doc = st.selectbox("Tipo:", ["Plano Ejecutivo (DWG/PDF)", "Memoria / Pliego", "Presupuesto Aprobado", "Acta de Replanteo", "Otro"])
                    codigo_plano = st.text_input("Código / Ref:", placeholder="Ej: ARQ-02")
                    revision = st.text_input("Revisión:", value="Rev.0")
                    destinatario = st.selectbox("Entregado a:", ["Empresa Constructora", "Promotor / Cliente", "Subcontrata Electricidad", "Subcontrata Fontanería", "Estructurista", "Otro"])
                    descripcion_doc = st.text_area("Observaciones:")
                    archivo_subido = st.file_uploader("Adjuntar Archivo:", type=["pdf", "dwg", "zip", "png", "jpg"])
                    if st.form_submit_button("Registrar Plano"):
                        if codigo_plano.strip() != "":
                            ruta_guardada = ""
                            if archivo_subido:
                                nombre_seguro = f"{datos_obra['codigo']}_{codigo_plano}_{revision}_{archivo_subido.name}".replace(" ", "_")
                                ruta_guardada = os.path.join(UPLOAD_DIR, nombre_seguro)
                                with open(ruta_guardada, "wb") as f: f.write(archivo_subido.getbuffer())
                            fecha_entrega = str(date.today())
                            cursor.execute("INSERT INTO documentos (obra_id, fecha_entrega, tipo_doc, codigo_plano, revision, destinatario, descripcion, archivo_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, fecha_entrega, tipo_doc, codigo_plano, revision, destinatario, descripcion_doc, ruta_guardada))
                            conn.commit()
                            st.rerun()

        with col_d2:
            st.markdown("#### 📑 Historial de Planos en Obra")
            if not df_docs.empty and rol == "Arquitecto" and est_exp == "En Curso / Activo":
                with st.expander("⚙️ Eliminar Plano / Documento del Historial"):
                    opc_doc = {f"ID {r['id']} - {r['codigo_plano']} (Rev. {r['revision']})": r['id'] for _, r in df_docs.iterrows()}
                    sel_doc = st.selectbox("Seleccionar plano obsoleto o erróneo:", list(opc_doc.keys()), key="sel_del_doc")
                    id_doc_sel = opc_doc[sel_doc]
                    if st.button("🗑️ Eliminar Documento", key="btn_del_doc"):
                        ruta_doc = df_docs[df_docs["id"] == id_doc_sel].iloc[0]["archivo_path"]
                        if ruta_doc and os.path.exists(ruta_doc):
                            try:
                                os.remove(ruta_doc) # Limpia el disco duro
                            except:
                                pass
                        cursor.execute("DELETE FROM documentos WHERE id = ?", (id_doc_sel,))
                        conn.commit()
                        st.warning("Plano eliminado del Entorno Común de Datos.")
                        st.rerun()
            if not df_docs.empty:
                st.dataframe(df_docs[["id", "fecha_entrega", "tipo_doc", "codigo_plano", "revision", "destinatario", "descripcion"]], width="stretch")
                for _, r_d in df_docs.iterrows():
                    if r_d["archivo_path"] and os.path.exists(r_d["archivo_path"]):
                        with open(r_d["archivo_path"], "rb") as f_desc:
                            bytes_data = f_desc.read()
                        
                        if rol == "Cliente":
                            if r_d["archivo_path"].lower().endswith(".pdf"):
                                with st.expander(f"👁️ Ver {r_d['codigo_plano']} (Modo Lectura)"):
                                    b64_pdf = base64.b64encode(bytes_data).decode('utf-8')
                                    pdf_display = f'<embed src="data:application/pdf;base64,{b64_pdf}#toolbar=0&navpanes=0&scrollbar=0" type="application/pdf" width="100%" height="800px" />'
                                    st.markdown(pdf_display, unsafe_allow_html=True)
                                    st.caption("🔒 Descarga deshabilitada por seguridad del documento.")
                            else:
                                with st.expander(f"👁️ Ver {r_d['codigo_plano']} (Modo Lectura)"):
                                    st.image(bytes_data, use_container_width=True)
                                    st.caption("🔒 Descarga deshabilitada por seguridad del documento.")
                        else:
                            col_btn1, col_btn2 = st.columns([1, 2])
                            with col_btn1:
                                st.download_button(label=f"⬇️ Descargar {r_d['codigo_plano']}", data=bytes_data, file_name=os.path.basename(r_d["archivo_path"]), key=f"btn_dl_{r_d['id']}")
                            with col_btn2:
                                if r_d["archivo_path"].lower().endswith(".pdf"):
                                    with st.expander("👁️ Abrir Visor Integrado"):
                                        b64_pdf = base64.b64encode(bytes_data).decode('utf-8')
                                        pdf_display = f'<embed src="data:application/pdf;base64,{b64_pdf}#toolbar=1&navpanes=0&view=FitH" type="application/pdf" width="100%" height="800px" />'
                                        st.markdown(pdf_display, unsafe_allow_html=True)
                                else:
                                    with st.expander("👁️ Abrir Visor Integrado"):
                                        st.image(bytes_data, use_container_width=True)
            else:
                st.info("Sin planos registrados.")

    # 4.4 Libro de Órdenes
    with subtab_ordenes:
        col_ord1, col_ord2 = st.columns([1, 2])
        with col_ord1:
            if est_exp == "En Curso / Activo" and rol in ["Arquitecto", "Constructor"]:
                st.markdown("#### 📝 Nueva Orden con Fotos")
                with st.form("form_incidencia_foto", clear_on_submit=True):
                    rol_emisor = st.selectbox("Actor:", ["Dirección Facultativa", "Jefe de Obra", "Subcontrata", "Promotor"], index=0 if rol=="Arquitecto" else 1)
                    prioridad = st.selectbox("Urgencia:", ["Baja", "Media", "Alta", "Paralización"])
                    descripcion = st.text_area("Descripción de la Orden:")
                    fotos_subidas = st.file_uploader("Fotografías de Obra:", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
                    if st.form_submit_button("Guardar en Bitácora"):
                        if descripcion.strip() != "":
                            rutas_guardadas = []
                            if fotos_subidas:
                                for idx_f, f_img_sub in enumerate(fotos_subidas):
                                    nombre_foto = f"FOTO_{datos_obra['codigo']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx_f}_{f_img_sub.name}".replace(" ", "_")
                                    ruta_foto = os.path.join(UPLOAD_DIR, nombre_foto)
                                    with open(ruta_foto, "wb") as f_out: f_out.write(f_img_sub.getbuffer())
                                    rutas_guardadas.append(ruta_foto)
                            fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
                            cursor.execute("INSERT INTO incidencias (obra_id, fecha, descripcion, rol_emisor, prioridad, estado, foto_path) VALUES (?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, fecha_hoy, descripcion, rol_emisor, prioridad, "Pendiente", ";".join(rutas_guardadas)))
                            conn.commit()
                            st.rerun()

            if not df_inc.empty and est_exp == "En Curso / Activo" and rol == "Arquitecto":
                st.divider()
                opciones_inc = {f"ID {row['id']} - {row['descripcion'][:30]}...": row['id'] for _, row in df_inc.iterrows()}
                sel_inc_txt = st.selectbox("Seleccionar orden:", list(opciones_inc.keys()))
                id_inc_sel = opciones_inc[sel_inc_txt]
                nuevo_est = st.selectbox("Estado Orden:", ["En Proceso", "Completada", "Cancelada", "Pendiente"])
                col_b1, col_b2 = st.columns(2)
                if col_b1.button("💾 Guardar"):
                    cursor.execute("UPDATE incidencias SET estado = ? WHERE id = ?", (nuevo_est, id_inc_sel))
                    conn.commit()
                    st.rerun()
                if col_b2.button("🗑️ Eliminar"):
                    cursor.execute("DELETE FROM incidencias WHERE id = ?", (id_inc_sel,))
                    conn.commit()
                    st.rerun()

        with col_ord2:
            st.markdown("#### 📋 Galería de Bitácora")
            if not df_inc.empty:
                for _, r_inc in df_inc.iterrows():
                    with st.expander(f"📌 #{r_inc['id']} | [{r_inc['estado']}] - {r_inc['descripcion'][:50]}..."):
                        st.write(f"**Emisor:** {r_inc['rol_emisor']} | **Prioridad:** {r_inc['prioridad']}")
                        st.write(r_inc['descripcion'])
                        rutas_str = r_inc.get("foto_path", "")
                        if rutas_str:
                            lista_rutas = [p for p in rutas_str.split(";") if p and os.path.exists(p)]
                            if lista_rutas:
                                cols_imgs = st.columns(min(len(lista_rutas), 3))
                                for idx_img, p_img in enumerate(lista_rutas):
                                    with cols_imgs[idx_img % 3]: st.image(p_img, use_container_width=True, caption=f"Foto {idx_img+1}")
            else:
                st.info("Sin órdenes en bitácora.")

# ---------------------------------------------------------
# FASE 5: LIQUIDACIÓN, RECEPCIÓN Y POSVENTA
# ---------------------------------------------------------
with tab_fase5:
    st.markdown("### 🏁 Fase 5: Cierre de Obra, Liquidación de Retenciones y Posventa")
    row_cierre = df_cierre.iloc[0] if not df_cierre.empty else None
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("#### 📜 Acta de Recepción y CFO")
        if est_exp == "En Curso / Activo" and rol == "Arquitecto":
            with st.form("form_cfo"):
                f_cfo_val = datetime.strptime(row_cierre["fecha_cfo"], "%Y-%m-%d").date() if row_cierre and row_cierre["fecha_cfo"] != "-" else date.today()
                f_recep_val = datetime.strptime(row_cierre["fecha_acta_recepcion"], "%Y-%m-%d").date() if row_cierre and row_cierre["fecha_acta_recepcion"] != "-" else date.today()
                f_cfo = st.date_input("Fecha Emisión CFO (Arquitecto):", value=f_cfo_val)
                f_recep = st.date_input("Fecha Firma Acta de Recepción:", value=f_recep_val)
                estado_cierre_val = row_cierre["estado_cierre"] if row_cierre else "En Ejecución (Obra Abierta)"
                nuevo_est_cierre = st.selectbox("Estado:", ["En Ejecución (Obra Abierta)", "Recepción Provisional con Remates", "Recepción Definitiva / Finalizada"], index=["En Ejecución (Obra Abierta)", "Recepción Provisional con Remates", "Recepción Definitiva / Finalizada"].index(estado_cierre_val))
                obs_cierre = st.text_area("Observaciones de Cierre / Remates pendientes:", value=row_cierre["observaciones"] if row_cierre else "")
                if st.form_submit_button("💾 Guardar Acta"):
                    cursor.execute("INSERT OR REPLACE INTO cierre_obra (obra_id, fecha_cfo, fecha_acta_recepcion, estado_cierre, retencion_devuelta, fecha_devolucion_retencion, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, str(f_cfo), str(f_recep), nuevo_est_cierre, row_cierre["retencion_devuelta"] if row_cierre else "No", row_cierre["fecha_devolucion_retencion"] if row_cierre else "-", obs_cierre))
                    conn.commit()
                    st.rerun()
        elif row_cierre:
             st.info(f"**Estado de Cierre:** {row_cierre['estado_cierre']} | **Fecha CFO:** {row_cierre['fecha_cfo']} | **Firma Acta:** {row_cierre['fecha_acta_recepcion']}")

    with col_c2:
        st.markdown("#### ⏳ Temporizador de Retención del 5%")
        st.write(f"**Fondo Retenido Acumulado:** `{total_retenciones:,.2f} €`")
        if row_cierre and row_cierre["fecha_acta_recepcion"] != "-" and row_cierre["estado_cierre"] != "En Ejecución (Obra Abierta)":
            f_recep_dt = datetime.strptime(row_cierre["fecha_acta_recepcion"], "%Y-%m-%d").date()
            f_vencimiento_garantia = f_recep_dt + timedelta(days=365)
            dias_restantes = (f_vencimiento_garantia - date.today()).days
            if dias_restantes > 0:
                st.info(f"🛡️ **Garantía Activa:** Quedan **{dias_restantes} días** para cumplir el año legal (Vence: {f_vencimiento_garantia.strftime('%d/%m/%Y')}).")
            else:
                st.success(f"✅ **Año Cumplido:** Procede la devolución de los {total_retenciones:,.2f} €.")
            
            if est_exp == "En Curso / Activo" and rol == "Arquitecto":
                with st.form("form_liberar_retencion"):
                    ret_dev = st.selectbox("¿Fondo 5% Devuelto a Contrata?:", ["No", "Sí (Liquidado)"], index=0 if row_cierre["retencion_devuelta"] == "No" else 1)
                    f_dev = st.date_input("Fecha Transferencia:", value=date.today())
                    if st.form_submit_button("Actualizar Devolución"):
                        cursor.execute("UPDATE cierre_obra SET retencion_devuelta = ?, fecha_devolucion_retencion = ? WHERE obra_id = ?", (ret_dev, str(f_dev), obra_id_activa))
                        conn.commit()
                        st.rerun()
        else:
            st.warning("Firma el Acta de Recepción para iniciar el contador de 365 días.")

    st.divider()
    col_pv1, col_pv2 = st.columns([1, 2])
    with col_pv1:
        if est_exp == "En Curso / Activo" and rol in ["Arquitecto", "Cliente"]:
            st.markdown("#### 🛠️ Registrar Reclamación Posventa")
            with st.form("form_nueva_posventa", clear_on_submit=True):
                f_aviso = st.date_input("Fecha Aviso:", value=date.today())
                elemento = st.text_input("Elemento Afectado:", placeholder="Ej: Filtración ventana")
                desc_pv = st.text_area("Descripción:")
                resp_pv = st.selectbox("Industrial Responsable:", ["Constructora Principal", "Carpintería / Vidrios", "Fontanería / Clima", "Electricidad", "Pintura y Acabados"])
                if st.form_submit_button("Guardar Reclamación"):
                    if elemento.strip() != "":
                        cursor.execute("INSERT INTO posventa (obra_id, fecha_aviso, elemento_afectado, descripcion, responsable, estado, fecha_resolucion) VALUES (?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, str(f_aviso), elemento, desc_pv, resp_pv, "Pendiente", "-"))
                        conn.commit()
                        st.rerun()

    with col_pv2:
        st.markdown("#### 📋 Bitácora de Posventa y Garantía")
        if not df_posventa.empty:
            st.dataframe(df_posventa[["id", "fecha_aviso", "elemento_afectado", "responsable", "estado", "fecha_resolucion"]], width="stretch")
            if est_exp == "En Curso / Activo" and rol == "Arquitecto":
                with st.expander("⚙️ Resolver Incidencia Posventa"):
                    opc_pv = {f"ID {r['id']} - {r['elemento_afectado'][:30]}": r['id'] for _, r in df_posventa.iterrows()}
                    sel_inc_txt = st.selectbox("Seleccionar:", list(opc_pv.keys()))
                    id_pv_sel = opc_pv[sel_inc_txt]
                    with st.form("form_resolver_pv"):
                        nuevo_est_pv = st.selectbox("Estado:", ["Pendiente", "En Reparación", "Subsanada y Conforme"])
                        f_res_pv = st.date_input("Fecha Resolución:", value=date.today())
                        cpv1, cpv2 = st.columns(2)
                        if cpv1.form_submit_button("💾 Guardar"):
                            cursor.execute("UPDATE posventa SET estado = ?, fecha_resolucion = ? WHERE id = ?", (nuevo_est_pv, str(f_res_pv) if nuevo_est_pv == "Subsanada y Conforme" else "-", id_pv_sel))
                            conn.commit()
                            st.rerun()
                        if cpv2.form_submit_button("🗑️ Eliminar"):
                            cursor.execute("DELETE FROM posventa WHERE id = ?", (id_pv_sel,))
                            conn.commit()
                            st.rerun()
        else:
            st.info("Sin incidencias posventa reportadas.")