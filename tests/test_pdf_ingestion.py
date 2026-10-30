import fitz
import pytest

from intelligent_scada.ingestion.pdf_analyzer import analyze_pdf
from intelligent_scada.ingestion.text_cleaner import clean_pages
from intelligent_scada.ingestion.text_extractor import extract_page_text


def make_pdf(path, *, text='Configure an alarm threshold.', toc=True):
    with fitz.open() as pdf:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
        if toc:
            pdf.set_toc([[1, 'Configuration', 1]])
        pdf.save(path)
    return path


def test_real_synthetic_pdf_analysis_and_text(tmp_path):
    pdf = make_pdf(tmp_path / 'synthetic.pdf')
    structure = analyze_pdf(pdf, tmp_path / 'structure.json')
    raw = extract_page_text(pdf, tmp_path / 'raw.json')
    pages = clean_pages(raw, tmp_path / 'clean.json', header_footer_patterns=(),
                        page_number_pattern=r'^\d+$')
    assert structure['total_pages'] == 1
    assert pages[0]['page'] == 1
    assert 'Configure an alarm threshold.' in pages[0]['clean_text']


@pytest.mark.parametrize(('text', 'toc'), [('Some text', False), ('', True)])
def test_unsupported_pdf_properties_are_reported(tmp_path, text, toc):
    pdf = make_pdf(tmp_path / 'unsupported.pdf', text=text, toc=toc)
    structure = analyze_pdf(pdf, tmp_path / 'structure.json')
    raw = extract_page_text(pdf, tmp_path / 'raw.json')
    assert bool(structure['toc']) is toc
    assert bool(raw[0]['raw_text'].strip()) is bool(text)
