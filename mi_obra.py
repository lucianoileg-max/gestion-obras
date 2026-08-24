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
import io
import os
import base64

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="ERP de Arquitectura y Dirección de Obra", layout="wide")

UPLOAD_DIR = "archivos_obra"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- BASE DE DATOS LOCAL ---
conn = sqlite3.connect("control_obras.db", check_same_thread=False)
cursor = conn.cursor()

# Tablas maestras
cursor.execute("CREATE TABLE IF NOT EXISTS obras (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, codigo TEXT, presupuesto_total REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS honorarios (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fase TEXT, porcentaje REAL, base_imponible REAL, iva REAL, retencion_irpf REAL, total_a_cobrar REAL, estado TEXT, fecha_emision TEXT, fecha_cobro TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS tramites (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, organismo TEXT, tipo_tramite TEXT, num_expediente TEXT, fecha_solicitud TEXT, fecha_limite TEXT, tasas_euros REAL, estado TEXT, observaciones TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS licitaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, capitulo TEXT, presupuesto_estimado REAL, empresa_a TEXT, oferta_a REAL, empresa_b TEXT, oferta_b REAL, empresa_c TEXT, oferta_c REAL, empresa_adjudicada TEXT, monto_adjudicado REAL, estado TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS certificaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, num_certificacion INTEGER, mes_ano TEXT, importe_bruto REAL, retencion_5pct REAL, liquido_pagar REAL, iva_21 REAL, total_factura REAL, estado TEXT, fecha_aprobacion TEXT, observaciones TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS cierre_obra (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER UNIQUE, fecha_cfo TEXT, fecha_acta_recepcion TEXT, estado_cierre TEXT, retencion_devuelta TEXT, fecha_devolucion_retencion TEXT, observaciones TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS posventa (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha_aviso TEXT, elemento_afectado TEXT, descripcion TEXT, responsable TEXT, estado TEXT, fecha_resolucion TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS incidencias (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha TEXT, descripcion TEXT, rol_emisor TEXT, prioridad TEXT, estado TEXT, foto_path TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS cronograma (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, etapa TEXT, tarea TEXT, fecha_inicio TEXT, fecha_fin TEXT, coste_estimado REAL, avance_porcentaje INTEGER DEFAULT 0, responsable TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS documentos (id INTEGER PRIMARY KEY AUTOINCREMENT, obra_id INTEGER, fecha_entrega TEXT, tipo_doc TEXT, codigo_plano TEXT, revision TEXT, destinatario TEXT, descripcion TEXT, archivo_path TEXT)")
conn.commit()

# --- GENERADOR DE INFORME PDF ---
def generar_informe_pdf(datos_obra, df_cronograma, df_incidencias, df_docs, df_honorarios, df_tramites, df_licit, df_cert, df_posventa):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    
    titulo_style = ParagraphStyle("Titulo", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#1A365D"), spaceAfter=10)
    subtitulo_style = ParagraphStyle("Subtitulo", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#2B6CB0"), spaceAfter=6)
    normal_style = styles["Normal"]

    story.append(Paragraph("INFORME INTEGRAL DE EXPEDIENTE Y DIRECCIÓN DE OBRA", titulo_style))
    story.append(Paragraph(f"<b>Proyecto:</b> {datos_obra['nombre']} | <b>Código:</b> {datos_obra['codigo']}", normal_style))
    story.append(Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
    story.append(Paragraph(f"<b>Presupuesto Ejecución Contratado:</b> {datos_obra['presupuesto_total']:,.2f} €", normal_style))
    story.append(Spacer(1, 10))

    if not df_honorarios.empty:
        story.append(Paragraph("1. FASE DE PROYECTO: Honorarios del Arquitecto", subtitulo_style))
        data_hon = [["Fase", "%", "Base (€)", "Total Factura (€)", "Estado"]]
        for _, r_h in df_honorarios.iterrows():
            data_hon.append([r_h["fase"][:25], f"{r_h['porcentaje']}%", f"{r_h['base_imponible']:,.2f} €", f"{r_h['total_a_cobrar']:,.2f} €", r_h["estado"]])
        t_hon = Table(data_hon, colWidths=[170, 45, 95, 105, 75])
        t_hon.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
        ]))
        story.append(t_hon)
        story.append(Spacer(1, 10))

    if not df_cert.empty:
        story.append(Paragraph("2. FASE DE OBRA: Certificaciones Mensuales de Contrata", subtitulo_style))
        data_c = [["Nº", "Periodo", "Bruto (€)", "Ret. 5% (€)", "Líquido (€)", "Estado"]]
        for _, rc in df_cert.iterrows():
            data_c.append([f"#{rc['num_certificacion']}", rc["mes_ano"], f"{rc['importe_bruto']:,.2f} €", f"{rc['retencion_5pct']:,.2f} €", f"{rc['liquido_pagar']:,.2f} €", rc["estado"]])
        t_c = Table(data_c, colWidths=[35, 95, 95, 85, 100, 80])
        t_c.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#CBD5E0")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
        ]))
        story.append(t_c)

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- BARRA LATERAL: SELECTOR DE PROYECTO ---
st.sidebar.title("🏛️ Despacho de Arquitectura")

with st.sidebar.expander("➕ Crear Nuevo Proyecto"):
    with st.form("form_nueva_obra", clear_on_submit=True):
        nuevo_nombre = st.text_input("Nombre del Proyecto:")
        nuevo_codigo = st.text_input("Código de Encargo:")
        nuevo_presupuesto = st.number_input("Presupuesto Ejecución Contrata (€):", min_value=0.0, step=5000.0, value=150000.0)
        if st.form_submit_button("Crear Proyecto") and nuevo_nombre.strip() != "":
            try:
                cursor.execute("INSERT INTO obras (nombre, codigo, presupuesto_total) VALUES (?, ?, ?)", (nuevo_nombre, nuevo_codigo, nuevo_presupuesto))
                conn.commit()
                st.rerun()
            except sqlite3.IntegrityError:
                st.sidebar.error("Ya existe un proyecto con ese nombre.")

obras_df = pd.read_sql_query("SELECT * FROM obras", conn)
if obras_df.empty:
    st.info("👈 Por favor, crea tu primer encargo desde la barra lateral.")
    st.stop()

opciones_obras = {f"{row['codigo']} - {row['nombre']}": row['id'] for _, row in obras_df.iterrows()}
obra_seleccionada_txt = st.sidebar.selectbox("Proyecto Activo:", list(opciones_obras.keys()))
obra_id_activa = opciones_obras[obra_seleccionada_txt]
datos_obra = obras_df[obras_df['id'] == obra_id_activa].iloc[0]

with st.sidebar.expander("✏️ Modificar Datos del Encargo"):
    with st.form("form_editar_obra"):
        edit_nombre_obra = st.text_input("Nombre:", value=datos_obra['nombre'])
        edit_codigo_obra = st.text_input("Código:", value=datos_obra['codigo'])
        edit_presupuesto_base = st.number_input("Presupuesto Ejecución (€):", value=float(datos_obra['presupuesto_total']), step=1000.0)
        if st.form_submit_button("Actualizar Datos"):
            cursor.execute("UPDATE obras SET nombre = ?, codigo = ?, presupuesto_total = ? WHERE id = ?", (edit_nombre_obra, edit_codigo_obra, edit_presupuesto_base, obra_id_activa))
            conn.commit()
            st.rerun()

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

# Cálculos consolidados
total_previsto = df_gantt["coste_estimado"].sum() if not df_gantt.empty else 0.0
total_fisico_euros = (df_gantt["coste_estimado"] * (df_gantt["avance_porcentaje"] / 100.0)).sum() if not df_gantt.empty else 0.0
pct_fisico_global = (total_fisico_euros / total_previsto * 100) if total_previsto > 0 else 0.0

total_cert_bruto = df_cert["importe_bruto"].sum() if not df_cert.empty else 0.0
pct_financiero_global = (total_cert_bruto / datos_obra["presupuesto_total"] * 100) if datos_obra["presupuesto_total"] > 0 else 0.0
total_retenciones = df_cert["retencion_5pct"].sum() if not df_cert.empty else 0.0
total_abonado_liquido = df_cert[df_cert["estado"] == "Abonada / Pagada"]["liquido_pagar"].sum() if not df_cert.empty else 0.0
saldo_contrata = datos_obra["presupuesto_total"] - total_cert_bruto
pendiente_certificar = max(0.0, total_fisico_euros - total_cert_bruto)

total_honorarios_base = df_honorarios["base_imponible"].sum() if not df_honorarios.empty else 0.0
total_tasas_pagadas = df_tramites["tasas_euros"].sum() if not df_tramites.empty else 0.0
inversion_total_cliente = datos_obra["presupuesto_total"] + total_honorarios_base + total_tasas_pagadas

# --- CABECERA PRINCIPAL ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.title(f"🏛️ Proyecto: {datos_obra['nombre']}")
    st.caption(f"Ref: {datos_obra['codigo']} | Inversión Total Cliente: **{inversion_total_cliente:,.2f} €** (Obra: {datos_obra['presupuesto_total']:,.0f} € + Honorarios: {total_honorarios_base:,.0f} € + Tasas: {total_tasas_pagadas:,.0f} €)")

with col_head2:
    st.write("")
    pdf_bytes = generar_informe_pdf(datos_obra, df_gantt, df_inc, df_docs, df_honorarios, df_tramites, df_licit, df_cert, df_posventa)
    st.download_button("📄 Descargar Expediente PDF", pdf_bytes, file_name=f"Expediente_{datos_obra['codigo']}.pdf", mime="application/pdf")

# ==========================================
# ESTRUCTURA POR 5 FASES CRONOLÓGICAS
# ==========================================
tab_fase1, tab_fase2, tab_fase3, tab_fase4, tab_fase5 = st.tabs([
    "📐 FASE 1: Proyecto y Honorarios",
    "🏛️ FASE 2: Licencias y Trámites",
    "⚖️ FASE 3: Licitación y Contratas",
    "🏗️ FASE 4: Ejecución y Dirección de Obra",
    "🏁 FASE 5: Cierre, Finiquito y Posventa"
])

# ---------------------------------------------------------
# FASE 1: PROYECTO Y HONORARIOS DEL ARQUITECTO
# ---------------------------------------------------------
with tab_fase1:
    st.markdown("### 📐 Fase 1: Redacción de Proyectos y Cobro de Honorarios")
    st.caption("Gestión económica de las minutas de honorarios profesionales por fases colegiales canónicas.")
    
    if not df_honorarios.empty:
        total_hon_base = df_honorarios["base_imponible"].sum()
        cobrado_base = df_honorarios[df_honorarios["estado"] == "Cobrado"]["base_imponible"].sum()
        pendiente_cobro = total_hon_base - cobrado_base
        cobrado_total_facturas = df_honorarios[df_honorarios["estado"] == "Cobrado"]["total_a_cobrar"].sum()

        h1, h2, h3 = st.columns(3)
        h1.metric("Honorarios Totales (Base)", f"{total_hon_base:,.2f} €")
        h2.metric("Total Cobrado en Banco (c/Impuestos)", f"{cobrado_total_facturas:,.2f} €")
        h3.metric("Honorarios Pendientes de Cobro", f"{pendiente_cobro:,.2f} €", delta=-pendiente_cobro)
        st.divider()

    with st.expander("⚡ Generar Fases de Honorarios Estándar (Colegial)", expanded=df_honorarios.empty):
        with st.form("form_auto_honorarios"):
            c_h1, c_h2, c_h3 = st.columns(3)
            with c_h1:
                hon_total_input = st.number_input("Honorarios Totales Pactados (€ Base):", min_value=1000.0, step=1000.0, value=12000.0)
            with c_h2:
                pct_iva = st.selectbox("% IVA aplicable:", [21, 10, 0], index=0)
            with c_h3:
                pct_irpf = st.selectbox("% Retención IRPF:", [15, 7, 0], index=0)

            if st.form_submit_button("🚀 Desglosar Fases de Honorarios"):
                cursor.execute("DELETE FROM honorarios WHERE obra_id = ?", (obra_id_activa,))
                fases_estandar = [
                    ("01. Estudios Previos y Anteproyecto", 15.0),
                    ("02. Proyecto Básico (Solicitud Licencia)", 20.0),
                    ("03. Proyecto Ejecutivo y Estructuras", 30.0),
                    ("04. Dirección de Obra y Liquidación Final", 35.0)
                ]
                for nom_fase, pct_fase in fases_estandar:
                    base_fase = round(hon_total_input * (pct_fase / 100.0), 2)
                    iva_fase = round(base_fase * (pct_iva / 100.0), 2)
                    irpf_fase = round(base_fase * (pct_irpf / 100.0), 2)
                    total_factura = round(base_fase + iva_fase - irpf_fase, 2)
                    cursor.execute("""
                        INSERT INTO honorarios (obra_id, fase, porcentaje, base_imponible, iva, retencion_irpf, total_a_cobrar, estado, fecha_emision, fecha_cobro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (obra_id_activa, nom_fase, pct_fase, base_fase, iva_fase, irpf_fase, total_factura, "Pendiente", "-", "-"))
                conn.commit()
                st.rerun()

    if not df_honorarios.empty:
        col_hon_tab, col_hon_act = st.columns([2, 1])
        with col_hon_tab:
            st.markdown("#### 📋 Cuadro de Minutas por Fases")
            st.dataframe(df_honorarios[["id", "fase", "porcentaje", "base_imponible", "iva", "retencion_irpf", "total_a_cobrar", "estado", "fecha_cobro"]], use_container_width=True)
        with col_hon_act:
            st.markdown("#### 💳 Registrar Cobro")
            opciones_h = {f"ID {r['id']} - {r['fase']} ({r['total_a_cobrar']:,.2f} €)": r['id'] for _, r in df_honorarios.iterrows()}
            sel_h_txt = st.selectbox("Selecciona Fase:", list(opciones_h.keys()))
            id_h_sel = opciones_h[sel_h_txt]
            with st.form("form_estado_cobro"):
                nuevo_estado_hon = st.selectbox("Estado de la Fase:", ["Pendiente", "Factura Emitida", "Cobrado"])
                f_cobro = st.date_input("Fecha de Cobro:", value=date.today())
                if st.form_submit_button("Actualizar Estado"):
                    txt_fcobro = str(f_cobro) if nuevo_estado_hon == "Cobrado" else "-"
                    cursor.execute("UPDATE honorarios SET estado = ?, fecha_cobro = ? WHERE id = ?", (nuevo_estado_hon, txt_fcobro, id_h_sel))
                    conn.commit()
                    st.rerun()

# ---------------------------------------------------------
# FASE 2: GESTIÓN MUNICIPAL Y VISADOS
# ---------------------------------------------------------
with tab_fase2:
    st.markdown("### 🏛️ Fase 2: Licencias, Visados y Requerimientos Administrativos")
    st.caption("Control de expedientes, semáforo de plazos con el Ayuntamiento y tasas abonadas.")

    if not df_tramites.empty:
        hoy_str = str(date.today())
        req_urgentes = df_tramites[(df_tramites["estado"] == "Requerimiento Pendiente") & (df_tramites["fecha_limite"] != "-") & (df_tramites["fecha_limite"] <= hoy_str)]
        if not req_urgentes.empty:
            for _, r_urg in req_urgentes.iterrows():
                st.error(f"🚨 **REQUERIMIENTO VENCIDO / URGENTE:** {r_urg['organismo']} - Exp: {r_urg['num_expediente']} (Plazo venció: {r_urg['fecha_limite']})")

        concedidas = len(df_tramites[df_tramites["estado"] == "Concedida / Favorable"])
        en_tramite = len(df_tramites[df_tramites["estado"].isin(["Presentado / En Trámite", "Requerimiento Pendiente"])])

        t1, t2, t3 = st.columns(3)
        t1.metric("Trámites en Curso", f"{en_tramite}")
        t2.metric("Licencias Concedidas", f"{concedidas}")
        t3.metric("Total Tasas / ICIO Pagadas", f"{total_tasas_pagadas:,.2f} €")
        st.divider()

    col_t_form, col_t_edit = st.columns(2)
    with col_t_form:
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
        with st.expander("⚙️ Actualizar o Eliminar Expediente"):
            if not df_tramites.empty:
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
                    if cb2.form_submit_button("🗑️ Eliminar"):
                        cursor.execute("DELETE FROM tramites WHERE id = ?", (id_tr_sel,))
                        conn.commit()
                        st.rerun()
            else:
                st.info("No hay trámites registrados.")

    if not df_tramites.empty:
        st.markdown("#### 📑 Historial Administrativo")
        st.dataframe(df_tramites[["id", "organismo", "tipo_tramite", "num_expediente", "fecha_solicitud", "fecha_limite", "tasas_euros", "estado", "observaciones"]], use_container_width=True)

# ---------------------------------------------------------
# FASE 3: CONTRATACIÓN Y LICITACIÓN
# ---------------------------------------------------------
with tab_fase3:
    st.markdown("### ⚖️ Fase 3: Cuadro Comparativo de Ofertas y Adjudicación")
    st.caption("Comparativa ciega de propuestas económicas de contratas principales e industriales.")
    
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
                    cursor.execute("INSERT INTO licitaciones (obra_id, capitulo, presupuesto_estimado, empresa_a, oferta_a, empresa_b, oferta_b, empresa_c, oferta_c, empresa_adjudicada, monto_adjudicado, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (obra_id_activa, capitulo_lic, pem_estimado, emp_a, ofert_a, emp_b, ofert_b, emp_c, ofert_c, "-", 0.0, "En Estudio"))
                    conn.commit()
                    st.rerun()

    with col_lic_adj:
        with st.expander("🏆 Adjudicar Oferta Ganadora"):
            if not df_licit.empty:
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
                    if col_adj2.form_submit_button("🗑️ Eliminar"):
                        cursor.execute("DELETE FROM licitaciones WHERE id = ?", (id_lic_sel,))
                        conn.commit()
                        st.rerun()
            else:
                st.info("No hay licitaciones activas.")

    if not df_licit.empty:
        st.markdown("#### 📋 Matriz de Licitaciones")
        st.dataframe(df_licit[["id", "capitulo", "presupuesto_estimado", "empresa_a", "oferta_a", "empresa_b", "oferta_b", "empresa_c", "oferta_c", "empresa_adjudicada", "monto_adjudicado", "estado"]], use_container_width=True)

# ---------------------------------------------------------
# FASE 4: DIRECCIÓN DE OBRA Y EJECUCIÓN MATERIAL
# ---------------------------------------------------------
with tab_fase4:
    st.markdown("### 🏗️ Fase 4: Dirección de Obra y Ejecución")
    st.caption("Planificación temporal, curva de inversión, certificaciones oficiales, planos ejecutivos y bitácora de órdenes.")

    subtab_gantt, subtab_cert, subtab_docs, subtab_ordenes = st.tabs([
        "📅 Cronograma y Curva S",
        "📑 Certificaciones Mensuales (5% Retención)",
        "📂 Planos y Entregas (CDE)",
        "📝 Libro de Órdenes y Fotografías"
    ])

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
                if st.form_submit_button("🚀 Generar Cronograma"):
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

        if not df_gantt.empty:
            df_gantt_plot = df_gantt.copy()
            df_gantt_plot["fecha_inicio_plot"] = pd.to_datetime(df_gantt_plot["fecha_inicio"])
            df_gantt_plot["fecha_fin_plot"] = pd.to_datetime(df_gantt_plot["fecha_fin"]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
            df_gantt_plot["Etiqueta_Avance"] = df_gantt_plot.apply(lambda r: f"{r['avance_porcentaje']}% ({(r['coste_estimado'] * r['avance_porcentaje'] / 100.0):,.0f} €)", axis=1)

            fig = px.timeline(df_gantt_plot, x_start="fecha_inicio_plot", x_end="fecha_fin_plot", y="tarea", color="etapa", text="Etiqueta_Avance", title="Diagrama de Gantt")
            fig.update_traces(textposition='inside', insidetextanchor='middle')
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)

            # Curva S
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
            
            fig_curva_s.add_hline(y=datos_obra["presupuesto_total"], line_dash="dash", line_color="#E53E3E", annotation_text=f"Presupuesto: {datos_obra['presupuesto_total']:,.0f} €", annotation_position="bottom right")
            fig_curva_s.update_layout(height=340, xaxis_title="Línea Temporal", yaxis_title="Euros (€)", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_curva_s, use_container_width=True)

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
            with st.expander("⚙️ Modificar Estado / Eliminar"):
                if not df_cert.empty:
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
                        if cb_c2.form_submit_button("🗑️ Eliminar"):
                            cursor.execute("DELETE FROM certificaciones WHERE id = ?", (id_cert_sel,))
                            conn.commit()
                            st.rerun()
                else:
                    st.info("No hay certificaciones emitidas.")

        if not df_cert.empty:
            st.dataframe(df_cert[["num_certificacion", "mes_ano", "importe_bruto", "retencion_5pct", "liquido_pagar", "iva_21", "total_factura", "estado", "fecha_aprobacion"]], use_container_width=True)

    # 4.3 Planos CDE
    with subtab_docs:
        col_d1, col_d2 = st.columns([1, 2])
        with col_d1:
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
                        nombre_seguro = f"{datos_obra['codigo']}_{codigo_plano}_{revision}_{archivo_subido.name}".replace(" ", "_") if archivo_subido else ""
                        if archivo_subido:
                            os.makedirs(UPLOAD_DIR, exist_ok=True)
                            ruta_guardada = os.path.join(UPLOAD_DIR, nombre_seguro)
                            with open(ruta_guardada, "wb") as f:
                                f.write(archivo_subido.getvalue())
                        cursor.execute("INSERT INTO documentos (obra_id, fecha_entrega, tipo_doc, codigo_plano, revision, destinatario, descripcion, archivo_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                       (obra_id_activa, str(date.today()), tipo_doc, codigo_plano, revision, destinatario, descripcion_doc, nombre_seguro))
                        conn.commit()
                        st.rerun()

        with col_d2:
            st.markdown("#### 📑 Historial de Planos en Obra")
            if not df_docs.empty:
                st.dataframe(df_docs[["id", "fecha_entrega", "tipo_doc", "codigo_plano", "revision", "destinatario", "descripcion"]], use_container_width=True)
                for _, r_d in df_docs.iterrows():
                    ruta_arch = r_d.get("archivo_path", "")
                    if ruta_arch:
                        ruta_fisica = os.path.join(UPLOAD_DIR, ruta_arch)
                        if os.path.exists(ruta_fisica):
                            with open(ruta_fisica, "rb") as f_desc:
                                bytes_data = f_desc.read()
                            st.download_button(
                                label=f"⬇️ Descargar {r_d['codigo_plano']} ({ruta_arch})",
                                data=bytes_data,
                                file_name=ruta_arch,
                                key=f"btn_dl_{r_d['id']}"
                            )
                        else:
                            st.caption(f"📁 Documento registrado: **{ruta_arch}** (Pendiente de subir en este dispositivo)")
            else:
                st.info("Sin planos registrados.")

    # 4.4 Libro de Órdenes
    with subtab_ordenes:
        col_ord1, col_ord2 = st.columns([1, 2])
        with col_ord1:
            st.markdown("#### 📝 Nueva Orden con Fotos")
            with st.form("form_incidencia_foto", clear_on_submit=True):
                rol = st.selectbox("Actor:", ["Dirección Facultativa", "Jefe de Obra", "Subcontrata", "Promotor"])
                prioridad = st.selectbox("Urgencia:", ["Baja", "Media", "Alta", "Paralización"])
                descripcion = st.text_area("Descripción de la Orden:")
                fotos_subidas = st.file_uploader("Fotografías de Obra:", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
                if st.form_submit_button("Guardar en Bitácora"):
                    if descripcion.strip() != "":
                        rutas_guardadas = []
                        if fotos_subidas:
                            os.makedirs(UPLOAD_DIR, exist_ok=True)
                            for idx_f, f_img_sub in enumerate(fotos_subidas):
                                nombre_foto = f"FOTO_{datos_obra['codigo']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx_f}_{f_img_sub.name}".replace(" ", "_")
                                ruta_foto = os.path.join(UPLOAD_DIR, nombre_foto)
                                with open(ruta_foto, "wb") as f_out: 
                                    f_out.write(f_img_sub.getvalue())
                                rutas_guardadas.append(ruta_foto)
                        cursor.execute("INSERT INTO incidencias (obra_id, fecha, descripcion, rol_emisor, prioridad, estado, foto_path) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                       (obra_id_activa, datetime.now().strftime("%Y-%m-%d %H:%M"), descripcion, rol, prioridad, "Pendiente", ";".join(rutas_guardadas)))
                        conn.commit()
                        st.rerun()

            todas_inc_df = pd.read_sql_query("SELECT id, descripcion, foto_path FROM incidencias WHERE obra_id = ?", conn, params=(obra_id_activa,))
            if not todas_inc_df.empty:
                st.divider()
                opciones_inc = {f"ID {row['id']} - {row['descripcion'][:30]}...": row['id'] for _, row in todas_inc_df.iterrows()}
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
                                    with cols_imgs[idx_img % 3]: 
                                        st.image(p_img, use_container_width=True, caption=f"Foto {idx_img+1}")
                            else:
                                st.caption("🖼️ *Fotos registradas en otra sesión/dispositivo.*")
            else:
                st.info("Sin órdenes en bitácora.")

# ---------------------------------------------------------
# FASE 5: LIQUIDACIÓN, RECEPCIÓN Y POSVENTA
# ---------------------------------------------------------
with tab_fase5:
    st.markdown("### 🏁 Fase 5: Cierre de Obra, Liquidación de Retenciones y Posventa")
    st.caption("Emisión del Certificado Final de Obra (CFO), devolución del 5% de retención y control de garantías.")

    row_cierre = df_cierre.iloc[0] if not df_cierre.empty else None
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("#### 📜 Acta de Recepción y CFO")
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
            st.dataframe(df_posventa[["id", "fecha_aviso", "elemento_afectado", "responsable", "estado", "fecha_resolucion"]], use_container_width=True)
            with st.expander("⚙️ Resolver Incidencia Posventa"):
                opc_pv = {f"ID {r['id']} - {r['elemento_afectado'][:30]}": r['id'] for _, r in df_posventa.iterrows()}
                sel_pv_txt = st.selectbox("Seleccionar:", list(opc_pv.keys()))
                id_pv_sel = opc_pv[sel_pv_txt]
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