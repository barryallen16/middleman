from pathlib import Path
from docling.document_converter import DocumentConverter
source = Path("timetable.jpeg")
converter = DocumentConverter()
result=converter.convert(source=source)
print(result.document.export_to_markdown())