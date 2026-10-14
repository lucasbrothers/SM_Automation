"""Small dependency-free XLSX report writer; text cells cannot become formulas."""
import re
import itertools
import math
import zipfile
from xml.sax.saxutils import escape,quoteattr


def column(index):
    name=''
    while index:
        index,rem=divmod(index-1,26);name=chr(65+rem)+name
    return name


def write_report(path,sheets):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        types=['<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>','<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        workbook=[];relations=[]
        for index,(name,rows) in enumerate(sheets,1):
            types.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
            workbook.append(f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>');relations.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
            iterator=iter(rows);header=next(iterator,[]);columns=max(1,len(header));last_row=0
            widths=''.join(f'<col min="{c}" max="{c}" width="{56 if c==columns else 28}" customWidth="1"/>' for c in range(1,columns+1))
            with archive.open(f'xl/worksheets/sheet{index}.xml','w') as output:
                output.write(('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>'+widths+'</cols><sheetData>').encode())
                for row_number,row in enumerate(itertools.chain([header],iterator),1):
                    if row_number>1048576:raise ValueError('Excel row limit exceeded; export smaller equipment books')
                    last_row=row_number;cells=[]
                    status=next((str(v) for v in row if str(v) in {'changed','added','removed','failed','변경','추가','삭제','실패'}),'')
                    style=1 if row_number==1 else {'changed':2,'변경':2,'added':3,'추가':3,'removed':4,'삭제':4,'failed':4,'실패':4}.get(status,0)
                    for col,value in enumerate(row,1):
                        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                            cells.append(f'<c r="{column(col)}{row_number}" s="{style}" t="n"><v>{value}</v></c>');continue
                        text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value if value is not None else ''))[:32767]
                        cells.append(f'<c r="{column(col)}{row_number}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
                    output.write((f'<row r="{row_number}">'+''.join(cells)+'</row>').encode())
                output.write(f'</sheetData><autoFilter ref="A1:{column(columns)}{max(1,last_row)}"/></worksheet>'.encode())
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(types)+'</Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(workbook)+'</sheets></workbook>')
        relations.append(f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(relations)+'</Relationships>')
        fills=['<fill><patternFill patternType="none"/></fill>','<fill><patternFill patternType="gray125"/></fill>']
        for color in ['17365D','FFF2CC','E2F0D9','FCE4D6']:fills.append('<fill><patternFill patternType="solid"><fgColor rgb="FF'+color+'"/><bgColor indexed="64"/></patternFill></fill>')
        styles=[]
        for font,fill in [(0,0),(1,2),(0,3),(0,4),(0,5)]:styles.append(f'<xf numFmtId="0" fontId="{font}" fillId="{fill}" borderId="0" xfId="0" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>')
        archive.writestr('xl/styles.xml','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="6">'+''.join(fills)+'</fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5">'+''.join(styles)+'</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
