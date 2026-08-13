# -*- coding: utf-8 -*-
"""Genera el PDF de la ficha de vacante/servicio (Headhunting u Outsourcing) + la JD."""
import os, io
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Flowable, KeepTogether, Table, TableStyle)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from PIL import Image
from _brand import _register_fonts, render_wordmark, FONTS

NAVY=HexColor("#202031"); PEARL=HexColor("#F0E8DE"); GOLD=HexColor("#FBE0A0")
GOLDLN=HexColor("#C8A84B"); TEAL=HexColor("#587579"); INK=HexColor("#2E2E38")
GRAY=HexColor("#8A8A92"); TRACK=HexColor("#E7E2D8"); LABEL=HexColor("#8FA6A8")

PAGE_W,PAGE_H=A4
LM=RM=42; HEADER_H=104; FOOTER_H=30
BODY_W=PAGE_W-LM-RM

WM_PEARL=os.path.join(FONTS,"wm_ficha_pearl.png")

def _hf(c, doc):
    c.saveState()
    c.setFillColor(NAVY); c.rect(0, PAGE_H-HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)
    # glow
    c.saveState()
    p=c.beginPath(); p.rect(0,PAGE_H-HEADER_H,PAGE_W,HEADER_H); c.clipPath(p,stroke=0,fill=0)
    c.setFillColor(GOLD)
    for r,a in ((70,.05),(50,.05),(34,.06),(20,.07)):
        c.setFillAlpha(a); c.circle(PAGE_W-8, PAGE_H-HEADER_H+4, r, fill=1, stroke=0)
    c.restoreState()
    iw,ih=Image.open(WM_PEARL).size; h=22; w=iw*(h/ih)
    c.drawImage(WM_PEARL, LM, PAGE_H-42, width=w, height=h, mask='auto', preserveAspectRatio=True)
    c.setFillColor(GOLD); c.setFont("Raleway-Md",7.5); c.drawString(LM, PAGE_H-56, "Better decisions, together.")
    c.setFillColor(PEARL); c.setFont("Raleway",8)
    c.drawRightString(PAGE_W-RM, PAGE_H-34, "tesseraservices.com")
    c.drawRightString(PAGE_W-RM, PAGE_H-46, "talent.operations@tesseraservices.com")
    if doc.page==1:
        c.saveState(); to=c.beginText(LM, PAGE_H-84); to.setFont("Raleway-Bd",9)
        to.setFillColor(LABEL); to.setCharSpace(2); to.textOut(getattr(doc,"_titulo","FICHA")); c.drawText(to)
        c.restoreState()
    c.setStrokeColor(GOLDLN); c.setLineWidth(2); c.line(0, PAGE_H-HEADER_H, PAGE_W, PAGE_H-HEADER_H)
    c.setStrokeColor(TRACK); c.setLineWidth(.7); c.line(LM, FOOTER_H+6, PAGE_W-RM, FOOTER_H+6)
    c.setFillColor(GRAY); c.setFont("Raleway",6.4)
    c.drawString(LM, FOOTER_H-4, "Tessera Human Capital  ·  Informaci\u00f3n tratada con confidencialidad  ·  Compromiso de feedback en 72 h.")
    c.drawString(LM, FOOTER_H-13, "tesseraservices.com")
    c.drawRightString(PAGE_W-RM, FOOTER_H-13, f"P\u00e1gina {doc.page}")
    c.restoreState()

class SectionHeader(Flowable):
    def __init__(self,t,w): super().__init__(); self.t=t; self.w=w; self.height=18
    def draw(self):
        c=self.canv; c.setFillColor(GOLDLN); c.rect(0,2,8,8,fill=1,stroke=0)
        c.setFillColor(NAVY); c.setFont("Raleway-Bd",10.5); c.drawString(15,3,self.t)
        tw=pdfmetrics.stringWidth(self.t,"Raleway-Bd",10.5)
        c.setStrokeColor(GOLDLN); c.setLineWidth(.9); c.line(15+tw+8,6,self.w,6)

def _st():
    return dict(
      lab=ParagraphStyle("lab",fontName="Raleway-Sb",fontSize=8.6,textColor=TEAL,leading=11.5),
      val=ParagraphStyle("val",fontName="Raleway",fontSize=9,textColor=INK,leading=12.6),
      body=ParagraphStyle("body",fontName="Raleway",fontSize=9,textColor=INK,leading=13.2),
      h=ParagraphStyle("h",fontName="Raleway-Bd",fontSize=9.4,textColor=NAVY,leading=12),
    )

def _esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _val_para(v, S):
    v=(v or "").strip() or "—"
    # respeta saltos de línea y viñetas
    v=_esc(v).replace("\n","<br/>")
    return Paragraph(v, S["val"])

def _fields(rows, S):
    data=[]
    for lab,val in rows:
        data.append([Paragraph(_esc(lab), S["lab"]), _val_para(val, S)])
    t=Table(data, colWidths=[BODY_W*0.34, BODY_W*0.66])
    t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LINEBELOW",(0,0),(-1,-2),0.4,TRACK)]))
    return t

def _section(title, rows, S, story):
    rows=[(l,v) for l,v in rows if v not in (None,"") and str(v).strip()]
    if not rows:
        return
    story.append(SectionHeader(title, BODY_W)); story.append(Spacer(1,5))
    story.append(_fields(rows, S)); story.append(Spacer(1,12))

def generar_ficha(data: dict) -> bytes:
    _register_fonts()
    render_wordmark("TESSERA",(240,232,222,255),WM_PEARL,tracking=10)
    S=_st(); tipo=data.get("tipo","headhunting")
    titulo = "FICHA DE VACANTE · HEADHUNTING" if tipo=="headhunting" else "FICHA DE SERVICIO · OUTSOURCING"

    story=[]
    # Empresa
    story.append(Paragraph(_esc(data.get("empresa","(empresa)")),
                 ParagraphStyle("emp",fontName="Times-Bold",fontSize=18,textColor=NAVY,leading=21)))
    sub=" · ".join([x for x in [data.get("sector",""), data.get("web","")] if x])
    if sub: story.append(Paragraph(_esc(sub), ParagraphStyle("sub",fontName="Raleway",fontSize=8.6,textColor=GRAY,leading=12)))
    story.append(Spacer(1,12))

    _section("DATOS DE CONTACTO", [
        ("Empresa", data.get("empresa","")),
        ("Sector", data.get("sector","")),
        ("Web de la empresa", data.get("web","")),
        ("Comercial de Tessera", data.get("sales_nombre","")),
        ("Email del comercial", data.get("sales_email","")),
    ], S, story)

    if data.get("empresa_resumen"):
        _section("SOBRE LA EMPRESA (resumen web)", [("Resumen", data.get("empresa_resumen",""))], S, story)

    if tipo=="headhunting":
        _section("EL ROL", [
            ("Título del puesto", data.get("titulo","")),
            ("Misión y responsabilidades", data.get("responsabilidades","")),
            ("Requisitos imprescindibles", data.get("requisitos","")),
            ("Idiomas necesarios", data.get("idiomas","")),
        ], S, story)
        _section("CONDICIONES DE CONTRATACIÓN", [
            ("Banda salarial fija", data.get("banda","")),
            ("Retribución variable", data.get("variable","")),
            ("Beneficios", data.get("beneficios","")),
            ("Modalidad", data.get("modalidad","")),
            ("Días presenciales/semana", data.get("dias_presenciales","")),
            ("Ubicación de la oficina", data.get("ubicacion","")),
            ("Horario de los empleados", data.get("horario","")),
        ], S, story)
        _section("EL PROCESO", [
            ("Fases de entrevista", data.get("fases","")),
            ("Pruebas técnicas o casos", data.get("pruebas","")),
            ("Interlocutor del proceso", data.get("interlocutor","")),
            ("Fecha objetivo de incorporación", data.get("fecha_inicio","")),
        ], S, story)
        _section("PARA ATRAER AL CANDIDATO", [
            ("Por qué unirse al proyecto", data.get("atraer","")),
        ], S, story)
    else:
        _section("EL ROL / SERVICIO", [
            ("Título del puesto o servicio", data.get("titulo","")),
            ("Misión y responsabilidades", data.get("responsabilidades","")),
            ("Requisitos imprescindibles", data.get("requisitos","")),
            ("Idiomas necesarios", data.get("idiomas","")),
        ], S, story)
        _section("CONDICIONES DEL SERVICIO", [
            ("Presupuesto mensual", data.get("presupuesto","")),
            ("Duración prevista", data.get("duracion","")),
            ("Fecha de inicio deseada", data.get("fecha_inicio","")),
            ("Renovación o ampliación", data.get("renovacion","")),
            ("Posible incorporación a plantilla", data.get("incorporacion","")),
            ("Modalidad", data.get("modalidad","")),
            ("Días presenciales/semana", data.get("dias_presenciales","")),
            ("Ubicación", data.get("ubicacion","")),
            ("Horario de los empleados", data.get("horario","")),
            ("Equipo y accesos", data.get("accesos","")),
        ], S, story)
        _section("ORGANIZACIÓN DEL DÍA A DÍA", [
            ("Responsable del día a día", data.get("responsable","")),
            ("Validación del perfil", data.get("validacion","")),
            ("Interlocutor del acuerdo", data.get("interlocutor","")),
        ], S, story)
        _section("SOBRE EL PROYECTO", [
            ("Descripción del proyecto", data.get("proyecto","")),
        ], S, story)

    # JD generada
    jd=(data.get("jd") or "").strip()
    if jd:
        story.append(SectionHeader("OFERTA (JD) GENERADA", BODY_W)); story.append(Spacer(1,6))
        for bloque in jd.split("\n"):
            b=bloque.strip("\r")
            if not b.strip():
                story.append(Spacer(1,5)); continue
            if b.strip().startswith(("•","-","*")):
                story.append(Paragraph("<font color='#587579'>•</font>&nbsp;&nbsp;"+_esc(b.strip()[1:].strip()),
                             ParagraphStyle("jdli",fontName="Raleway",fontSize=9,textColor=INK,leading=13,
                                            leftIndent=12,firstLineIndent=-12)))
            elif b.strip().isupper() or b.strip().endswith(":") or b.strip() in (
                 "Quiénes somos","El reto","Requisitos","Será un plus si","Qué se ofrece","Nota sobre el proceso"):
                story.append(Spacer(1,3))
                story.append(Paragraph(_esc(b.strip()), S["h"]))
            else:
                story.append(Paragraph(_esc(b), S["body"]))

    buf=io.BytesIO()
    doc=BaseDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=RM,
                        topMargin=HEADER_H+16, bottomMargin=FOOTER_H+14)
    doc._titulo=titulo
    frame=Frame(LM, FOOTER_H+14, BODY_W, PAGE_H-HEADER_H-FOOTER_H-30, id='b')
    doc.addPageTemplates([PageTemplate(id='m', frames=[frame], onPage=_hf)])
    doc.build(story)
    return buf.getvalue()
