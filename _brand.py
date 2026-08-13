# -*- coding: utf-8 -*-
"""
Generador del Informe de Candidato de Tessera (ReportLab + PIL).
Se reutiliza tal cual desde la app de Streamlit.

Fuentes necesarias en ./fonts:
  - Ailerons-Typeface.otf      (wordmark TESSERA, obligatorio, sin fallback)
  - Raleway-VF.ttf             (variable font; se instancian los pesos al arrancar)
Si ya tienes los pesos estaticos Raleway-*.ttf, tambien los usa.
"""
import os, io
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, Flowable, KeepTogether)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
WORDMARK = os.path.join(FONTS, "wordmark_tessera.png")

# ---- Brand ----
NAVY=HexColor("#202031"); PEARL=HexColor("#F0E8DE"); WHITE=HexColor("#FFFFFF")
GOLD=HexColor("#FBE0A0"); GOLDLN=HexColor("#C8A84B")   # dorado mostaza (cuadrados y reglas)
TEAL=HexColor("#587579"); GRANATE=HexColor("#762D35")
INK=HexColor("#2E2E38"); GRAY=HexColor("#8A8A92"); TRACK=HexColor("#E7E2D8")
LABEL=HexColor("#8FA6A8")   # teal grisaceo para "PERFIL DE CANDIDATO"

# ---------------- Font bootstrap ----------------
def _ensure_raleway():
    weights = {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700,"ExtraBold":800}
    need = [w for w in weights if not os.path.exists(os.path.join(FONTS, f"Raleway-{w}.ttf"))]
    if not need:
        return
    vf = os.path.join(FONTS, "Raleway-VF.ttf")
    if not os.path.exists(vf):
        raise FileNotFoundError("Falta fonts/Raleway-VF.ttf (o los Raleway-*.ttf estaticos).")
    from fontTools.ttLib import TTFont as FTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    for w in need:
        f = FTFont(vf)
        instantiateVariableFont(f, {"wght": weights[w]}, inplace=True)
        f.save(os.path.join(FONTS, f"Raleway-{w}.ttf"))

def render_wordmark(text="TESSERA", color=(240,232,222,255), out_path=None, fs=240, tracking=0):
    """Renderiza un wordmark en Ailerons (sin fallback). Devuelve la ruta del PNG."""
    otf = os.path.join(FONTS, "Ailerons-Typeface.otf")
    if not os.path.exists(otf):
        raise FileNotFoundError("Falta fonts/Ailerons-Typeface.otf (sin fallback permitido).")
    font = ImageFont.truetype(otf, fs)
    pad = 20
    if tracking:
        # render letra a letra con espaciado extra
        widths = []; total = 0; h = 0; top = 0
        for ch in text:
            b = font.getbbox(ch); widths.append(b[2]-b[0]); total += (b[2]-b[0]) + tracking
            h = max(h, b[3]-b[1]); top = min(top, b[1])
        total -= tracking
        img = Image.new("RGBA",(total+pad*2, fs+pad), (0,0,0,0))
        d = ImageDraw.Draw(img); x = pad
        for ch in text:
            d.text((x, pad), ch, font=font, fill=color); b = font.getbbox(ch)
            x += (b[2]-b[0]) + tracking
        img = img.crop(img.getbbox())
    else:
        tmp = Image.new("RGBA",(10,10)); d=ImageDraw.Draw(tmp)
        bbox = d.textbbox((0,0), text, font=font)
        w=bbox[2]-bbox[0]; h=bbox[3]-bbox[1]
        img = Image.new("RGBA",(w+pad*2,h+pad*2),(0,0,0,0))
        d=ImageDraw.Draw(img)
        d.text((pad-bbox[0],pad-bbox[1]),text,font=font,fill=color)
        img = img.crop(img.getbbox())
    out = out_path or os.path.join(FONTS, f"wordmark_{text}.png")
    img.save(out)
    return out

def _ensure_wordmark():
    if not os.path.exists(WORDMARK):
        render_wordmark("TESSERA", (240,232,222,255), WORDMARK)

_FONTS_READY = False
def _register_fonts():
    global _FONTS_READY
    if _FONTS_READY:
        return
    _ensure_raleway(); _ensure_wordmark()
    pairs = {"Raleway":"Regular","Raleway-Lt":"Light","Raleway-Md":"Medium",
             "Raleway-Sb":"SemiBold","Raleway-Bd":"Bold","Raleway-Xb":"ExtraBold"}
    for name,w in pairs.items():
        pdfmetrics.registerFont(TTFont(name, os.path.join(FONTS, f"Raleway-{w}.ttf")))
    _FONTS_READY = True

# ---------------- Geometry (A4 7.5x10.6 = 540x763, como el modelo) ----------------
PAGE_W, PAGE_H = 540, 763
LM=36; RM=36; HEADER_H=112; FOOTER_H=30
body_w = PAGE_W - LM - RM

# ---------------- Header / Footer ----------------
LABELS = {
  "es": {"cand": "PERFIL DE CANDIDATO", "perfil": "PERFIL PROFESIONAL",
         "comp": "COMPETENCIAS RELACIONADAS", "exp": "EXPERIENCIA PROFESIONAL",
         "formc": "FORMACI\u00d3N COMPLEMENTARIA", "formid": "FORMACI\u00d3N E IDIOMAS",
         "foot": ("Documento confidencial. Elaborado por Tessera Human Capital para uso exclusivo del "
                  "cliente destinatario. Prohibida su reproducci\u00f3n o distribuci\u00f3n."),
         "pag": "P\u00e1gina"},
  "en": {"cand": "CANDIDATE PROFILE", "perfil": "PROFESSIONAL PROFILE",
         "comp": "KEY SKILLS", "exp": "PROFESSIONAL EXPERIENCE",
         "formc": "ADDITIONAL TRAINING", "formid": "EDUCATION & LANGUAGES",
         "foot": ("Confidential document. Prepared by Tessera Human Capital for the exclusive use of the "
                  "intended client. Reproduction or distribution is prohibited."),
         "pag": "Page"},
}

def _header_footer(c, doc):
    c.saveState()
    # banda navy
    c.setFillColor(NAVY); c.rect(0, PAGE_H-HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)
    # glow dorado sutil, confinado a la banda
    c.saveState()
    pth=c.beginPath(); pth.rect(0, PAGE_H-HEADER_H, PAGE_W, HEADER_H); c.clipPath(pth, stroke=0, fill=0)
    c.setFillColor(GOLD)
    for r,a in ((72,0.05),(54,0.05),(38,0.06),(24,0.07)):
        c.setFillAlpha(a); c.circle(PAGE_W-8, PAGE_H-HEADER_H+4, r, fill=1, stroke=0)
    c.restoreState()
    # wordmark pearl
    iw,ih = Image.open(WORDMARK).size; th=22; tw=iw*(th/ih)
    c.drawImage(WORDMARK, LM, PAGE_H-40, width=tw, height=th, mask='auto', preserveAspectRatio=True)
    c.setFillColor(GOLD); c.setFont("Raleway-Md",7.5)
    c.drawString(LM, PAGE_H-54, "Better decisions, together.")
    # contacto arriba-derecha
    c.setFillColor(PEARL); c.setFont("Raleway",8)
    c.drawRightString(PAGE_W-RM, PAGE_H-34, "tesseraservices.com")
    c.drawRightString(PAGE_W-RM, PAGE_H-46, "info@tesseraservices.com")
    _lab = LABELS.get(getattr(doc, "_lang", "es"), LABELS["es"])
    # etiqueta de perfil + nombre (solo pagina 1)
    if doc.page == 1:
        c.saveState()
        to=c.beginText(LM, PAGE_H-82); to.setFont("Raleway-Bd",9)
        to.setFillColor(LABEL); to.setCharSpace(2.2); to.textOut(_lab["cand"])
        c.drawText(to)
        c.restoreState()
        nombre = getattr(doc, "_cand_nombre", "")
        c.setFillColor(PEARL); c.setFont("Times-Bold", 23)
        c.drawString(LM, PAGE_H-106, nombre)
    # regla dorada bajo la banda
    c.setStrokeColor(GOLDLN); c.setLineWidth(2)
    c.line(0, PAGE_H-HEADER_H, PAGE_W, PAGE_H-HEADER_H)
    # footer
    c.setStrokeColor(TRACK); c.setLineWidth(0.7)
    c.line(LM, FOOTER_H+6, PAGE_W-RM, FOOTER_H+6)
    c.setFillColor(GRAY); c.setFont("Raleway",6.2)
    c.drawString(LM, FOOTER_H-4, _lab["foot"])
    c.drawString(LM, FOOTER_H-13, "tesseraservices.com")
    c.drawRightString(PAGE_W-RM, FOOTER_H-13, f'{_lab["pag"]} {doc.page}')
    c.restoreState()

# ---------------- Flowables ----------------
class SectionHeader(Flowable):
    def __init__(self, title, width): super().__init__(); self.title=title; self.width=width; self.height=17
    def draw(self):
        c=self.canv
        c.setFillColor(GOLDLN); c.rect(0, 2, 8, 8, fill=1, stroke=0)          # cuadrado mostaza
        c.setFillColor(NAVY); c.setFont("Raleway-Bd",10.5); c.drawString(15, 3, self.title)
        tw=pdfmetrics.stringWidth(self.title,"Raleway-Bd",10.5)
        c.setStrokeColor(GOLDLN); c.setLineWidth(0.9); c.line(15+tw+8, 6, self.width, 6)

class TealBar(Flowable):
    def __init__(self,label,pct,width): super().__init__(); self.label=label; self.pct=pct; self.width=width; self.height=22
    def draw(self):
        c=self.canv; c.setFillColor(INK); c.setFont("Raleway-Sb",8.5); c.drawString(0,13,self.label)
        c.setFillColor(TRACK); c.roundRect(0,3,self.width,5,2.5,fill=1,stroke=0)
        c.setFillColor(TEAL); c.roundRect(0,3,self.width*self.pct,5,2.5,fill=1,stroke=0)

def _pill(text):
    class Pill(Flowable):
        def __init__(self,label):
            super().__init__(); self.label=label
            self.tw=pdfmetrics.stringWidth(label,"Raleway-Sb",8.5)
            self.width=max(self.tw+40,150); self.height=22
        def draw(self):
            c=self.canv; w=self.width
            c.setFillColor(TEAL); c.roundRect(0,0,w,19,9.5,fill=1,stroke=0)
            c.setFillColor(WHITE); c.setFont("Raleway-Sb",8.5)
            c.drawCentredString(w/2,6,self.label)
    return Pill(text)

# ---------------- Styles ----------------
def _styles():
    return dict(
      body=ParagraphStyle("body",fontName="Raleway",fontSize=9,textColor=INK,leading=13.2,alignment=TA_LEFT),
      comp=ParagraphStyle("comp",fontName="Raleway",fontSize=8.6,textColor=INK,leading=12,
                           leftIndent=13,firstLineIndent=-13),
      erole=ParagraphStyle("erole",fontName="Raleway",fontSize=9.2,textColor=INK,leading=12.5),
      edate=ParagraphStyle("edate",fontName="Raleway",fontSize=7.8,textColor=GRAY,leading=12.5,alignment=2),
      li=ParagraphStyle("li",fontName="Raleway",fontSize=8.3,textColor=INK,leading=11.8,
                        leftIndent=13,firstLineIndent=-13),
      cert_code=ParagraphStyle("cc",fontName="Raleway-Bd",fontSize=8.3,textColor=TEAL,leading=12),
      cert_desc=ParagraphStyle("cd",fontName="Raleway",fontSize=8.3,textColor=INK,leading=12),
      cert_date=ParagraphStyle("cdt",fontName="Raleway",fontSize=7.8,textColor=GRAY,leading=12,alignment=2),
      et=ParagraphStyle("et",fontName="Raleway-Sb",fontSize=8.8,textColor=NAVY,leading=11.5),
      ei=ParagraphStyle("ei",fontName="Raleway",fontSize=7.8,textColor=TEAL,leading=10),
      enote=ParagraphStyle("en",fontName="Raleway-It" if False else "Raleway",fontSize=7,textColor=GRAY,leading=9.5,spaceAfter=6),
    )

def _esc(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

import re as _re
def _nivel_pct(label, fallback=0.5):
    """Deduce el llenado de la barra a partir del nivel escrito en la etiqueta."""
    t = str(label).lower()
    if _re.search(r"\bnativ|bilin", t):        return 1.0
    m = _re.search(r"\b([abc][12])\b", t)      # C2, C1, B2, B1, A2, A1
    if m:
        return {"c2":0.95,"c1":0.82,"b2":0.66,"b1":0.5,"a2":0.34,"a1":0.2}[m.group(1)]
    if _re.search(r"fluid|avanzad|profesional|full", t): return 0.85
    if _re.search(r"interm", t):               return 0.6
    if _re.search(r"b\u00e1sic|basic|element", t): return 0.3
    try:
        v = float(fallback);  return max(0.05, min(1.0, v))
    except Exception:
        return 0.5

def _bullet(text, S):
    return Paragraph(f'<font size="11" color="#587579">&#8226;</font>&nbsp;&nbsp;{_esc(text)}', S["comp"])

def _two_col(items, S, cell=_bullet):
    cc=items[:]
    if len(cc)%2: cc.append("")
    rows=[[cell(cc[i],S) if cc[i] else Paragraph("",S["comp"]),
           cell(cc[i+1],S) if cc[i+1] else Paragraph("",S["comp"])] for i in range(0,len(cc),2)]
    t=Table(rows,colWidths=[body_w/2, body_w/2])
    t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3.5),
                           ("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),0),
                           ("RIGHTPADDING",(0,0),(0,0),14)]))
    return t

# ---------------- Public API ----------------
def generar_informe(data: dict, lang: str = "es") -> bytes:
    _register_fonts(); S=_styles()
    LB = LABELS.get(lang, LABELS["es"])
    story=[]
    story.append(_pill(str(data.get("rol",""))))
    if data.get("ubicacion"):
        story.append(Spacer(1,4))
        story.append(Paragraph(_esc(data["ubicacion"]),
                     ParagraphStyle("loc",fontName="Raleway",fontSize=8.4,textColor=GRAY,leading=11)))
    story.append(Spacer(1,15))

    # PERFIL
    story.append(SectionHeader(LB["perfil"], body_w)); story.append(Spacer(1,7))
    story.append(Paragraph(_esc(data.get("perfil","")), S["body"])); story.append(Spacer(1,14))

    # COMPETENCIAS
    comps=data.get("competencias",[])
    if comps:
        story.append(SectionHeader(LB["comp"], body_w)); story.append(Spacer(1,7))
        story.append(_two_col(comps,S)); story.append(Spacer(1,14))

    # EXPERIENCIA
    exps=data.get("experiencias",[])
    if exps:
        story.append(SectionHeader(LB["exp"], body_w)); story.append(Spacer(1,8))
        for e in exps:
            role=_esc(e.get("role","")); comp=_esc(e.get("company","")); meta=_esc(e.get("meta",""))
            left=Paragraph(f'<font name="Raleway-Sb" color="#202031">{role}</font>'
                           f'<font color="#587579">&nbsp;&#183;&nbsp;{comp}</font>', S["erole"])
            right=Paragraph(meta, S["edate"])
            row=Table([[left,right]],colWidths=[body_w*0.70, body_w*0.30])
            row.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),
                                     ("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),
                                     ("BOTTOMPADDING",(0,0),(-1,-1),2)]))
            blk=[row]
            for b in e.get("bullets",[]) or []:
                blk.append(Paragraph(f'<font size="11" color="#587579">&#8226;</font>&nbsp;&nbsp;{_esc(b)}', S["li"]))
            blk.append(Spacer(1,9))
            story.append(KeepTogether(blk))
        story.append(Spacer(1,4))

    # CERTIFICACIONES / FORMACION COMPLEMENTARIA (opcional)
    fc=data.get("formacion_complementaria")
    if fc:
        story.append(SectionHeader(LB["formc"], body_w)); story.append(Spacer(1,7))
        story.append(_two_col(fc,S)); story.append(Spacer(1,14))

    # FORMACION E IDIOMAS
    story.append(SectionHeader(LB["formid"], body_w)); story.append(Spacer(1,8))
    left_w=body_w*0.56; right_w=body_w*0.44
    form_blk=[]
    for item in data.get("formacion",[]):
        titulo, meta = (item+["",""])[:2] if isinstance(item,list) else (item.get("titulo",""),item.get("meta",""))
        form_blk.append(Paragraph(_esc(titulo), S["et"]))
        form_blk.append(Paragraph(_esc(meta), S["ei"]))
        form_blk.append(Spacer(1,7))
    idi_blk=[]; idiomas=data.get("idiomas",[])
    for j,it in enumerate(idiomas):
        lab,pct=(it+[1.0])[:2] if isinstance(it,list) else (it.get("label",""),it.get("pct",1.0))
        idi_blk.append(TealBar(_esc(lab), _nivel_pct(lab, pct), right_w-8))
    ftab=Table([[form_blk, idi_blk]], colWidths=[left_w,right_w])
    ftab.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(0,0),0),
                              ("LEFTPADDING",(1,0),(1,0),16),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story.append(ftab)

    buf=io.BytesIO()
    doc=BaseDocTemplate(buf, pagesize=(PAGE_W,PAGE_H), leftMargin=LM, rightMargin=RM,
                        topMargin=HEADER_H+16, bottomMargin=FOOTER_H+14)
    doc._cand_nombre = str(data.get("nombre",""))
    doc._lang = lang
    frame=Frame(LM, FOOTER_H+14, body_w, PAGE_H-HEADER_H-FOOTER_H-30, id='body')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=_header_footer)])
    doc.build(story)
    return buf.getvalue()
