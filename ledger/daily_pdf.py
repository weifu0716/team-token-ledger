"""Generate a local PDF; no model calls or remote assets."""
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


def render(report, path, font_path=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

    candidate = Path(font_path) if font_path else Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msjh.ttc'
    font = 'DailyCJK'
    if candidate.exists():
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font, str(candidate), subfontIndex=0))
    else:
        font = 'MSung-Light'
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(font))
    normal = ParagraphStyle('body', fontName=font, fontSize=10, leading=16, textColor=colors.HexColor('#233c35'), wordWrap='CJK')
    heading = ParagraphStyle('heading', parent=normal, fontSize=22, leading=30, spaceAfter=10)
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=12, textColor=colors.HexColor('#52685f'))
    def p(text, style=normal):
        return Paragraph(escape(str(text)), style)
    t = report['totals']
    start = datetime.fromisoformat(report['start']).strftime('%m/%d %H:%M')
    end = datetime.fromisoformat(report['end']).strftime('%m/%d %H:%M')
    offset = datetime.fromisoformat(report['start']).strftime('%z')
    story = [p('每日 AI 使用紀錄', heading), p(f"{report['name']}　／　{report['day']}"),
             p(f"統計區間：{start} 至 {end}（UTC{offset}；結束時間不含）", small),
             p('整日結算' if report['complete_day'] else '當日截至目前；之後的使用會在更新或補產時納入', small), Spacer(1, 6*mm)]
    cells = [[p('已觀測總 Token'), p(f"{t['total_tokens']:,}")],
             [p('輸入 Token'), p(f"{t['input_tokens']:,}")],
             [p('其中快取（已含在輸入）'), p(f"{t['cached_input_tokens']:,}")],
             [p('輸出 Token'), p(f"{t['output_tokens']:,}")]]
    table = Table(cells, colWidths=[110*mm, 55*mm])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6eee6')),('BOTTOMPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),9),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#d4ddd4'))]))
    story += [table, Spacer(1,6*mm),p('工作線索（不代表已完成成果）')]
    if not report['tasks']:
        story.append(p('此區間沒有可計入的工作紀錄；請同時查看來源狀態。', small))
    for task in report['tasks'][:20]:
        story += [Spacer(1,3*mm), KeepTogether([p(f"{task['project']}　／　{task['total_tokens']:,} Token"),p(task['text'] or '未開啟工作原文片段分享。',small)])]
    if len(report['tasks']) > 20:
        story.append(p(f"另有 {len(report['tasks'])-20} 個工作項目，全部小計仍含在總數與核對檔。",small))
    story += [Spacer(1,6*mm),p('資料與核對狀態')]
    story.append(p(f"可讀來源檔案：{report['source_files']}；去重後用量事件：{len(report['events'])}。",small))
    for warning in report['warnings']:
        story.append(p('待核對：'+warning,small))
    story += [p('總數按輸入＋輸出計算；快取不重複相加。老闆收件時會重算明細並核對PDF指紋。',small),
              p('這是本機紀錄觀測值，不等於訂閱額度、費用、工時或績效。核對通過不保證原始紀錄未被修改。',small)]
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=22*mm, leftMargin=22*mm, topMargin=19*mm, bottomMargin=19*mm,
                            title=f"{report['name']} {report['day']} AI日報", author='Team Token Ledger')
    def footer(canvas, document):
        canvas.setFont(font,8)
        canvas.setFillColor(colors.HexColor('#52685f'))
        canvas.drawString(22*mm,12*mm,'Team Token Ledger / 0.2.0 · 自動產生，未呼叫模型')
        canvas.drawRightString(188*mm,12*mm,str(document.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
