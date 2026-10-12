"""Simple client inventory XLSX import/export without formulas or macros."""
import csv
import io
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

HEADERS = ["hostname", "ip", "os", "profile"]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

def save(path, records):
    rows=[HEADERS]+[[str(r.get(k,"default" if k=="profile" else "")) for k in HEADERS] for r in records]
    xml=[]
    for n,row in enumerate(rows,1):
        cells="".join(f'<c r="{chr(65+i)}{n}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for i,v in enumerate(row))
        xml.append(f'<row r="{n}">{cells}</row>')
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Clients" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="4" width="28" customWidth="1"/></cols><sheetData>'+"".join(xml)+'</sheetData><autoFilter ref="A1:D'+str(len(rows))+'"/></worksheet>')

def read_csv(path):
    with zipfile.ZipFile(path) as z:
        if len(z.infolist())>1000 or sum(i.file_size for i in z.infolist())>16*1024*1024:
            raise ValueError("Workbook is too large")
        shared=[]
        if "xl/sharedStrings.xml" in z.namelist():
            shared=["".join(s.itertext()) for s in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si",NS)]
        workbook=ET.fromstring(z.read("xl/workbook.xml"))
        sheet=workbook.find("m:sheets/m:sheet",NS)
        relid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target=next(r.attrib['Target'] for r in rels if r.attrib['Id']==relid)
        sheet_path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        root=ET.fromstring(z.read(sheet_path))
        output=io.StringIO(); writer=csv.writer(output)
        for row in root.findall('m:sheetData/m:row',NS):
            values=['']*4
            for cell in row.findall('m:c',NS):
                if cell.find('m:f',NS) is not None:raise ValueError("Inventory cells must contain values, not formulas")
                col=''.join(c for c in cell.attrib.get('r','') if c.isalpha())
                if col not in 'ABCD' or len(col)!=1:continue
                value=cell.findtext('m:v','',NS)
                if cell.attrib.get('t')=='s':value=shared[int(value)]
                elif cell.attrib.get('t')=='inlineStr':value=''.join(cell.find('m:is',NS).itertext())
                values[ord(col)-65]=value
            if any(values):writer.writerow(values)
    return output.getvalue()
