"""Automatic, bounded tabular preparation. Source bytes are never evaluated."""
from __future__ import annotations
import csv
from collections import Counter
import datetime as dt
import io
import math
import re
import zipfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 100
MAX_CELLS = 1_000_000


class InputError(ValueError):
    def __init__(self, message, code="invalid_input", details=None):
        super().__init__(message)
        self.code, self.details = code, details or {}


def numeric(value):
    text = str(value).strip()
    negative = text.startswith('(') and text.endswith(')')
    text = text.strip('()').strip()
    currency = next((symbol for symbol in '$€£' if text.startswith(symbol)), None)
    if currency:
        text = text[1:].strip()
    percent = text.endswith('%')
    if percent:
        text = text[:-1].strip()
    if ',' in text:
        if not re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?', text):
            return None
        text = text.replace(',', '')
    if not re.fullmatch(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?', text):
        return None
    number = float(text) * (-1 if negative else 1) / (100 if percent else 1)
    if not math.isfinite(number):
        raise InputError('The data contains non-finite numbers.')
    return number, ('ratio' if percent else {'$':'USD','€':'EUR','£':'GBP'}.get(currency))


def is_date(value):
    return isinstance(value, (dt.date, dt.datetime)) or bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[ T].*)?', str(value)))


def header_candidate(rows):
    choices = []
    for i, row in enumerate(rows[:50]):
        cells = [str(x).strip() if x is not None else '' for x in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells or any(not x for x in cells) or len(set(x.casefold() for x in cells)) != len(cells):
            continue
        if any(numeric(x) is not None or is_date(x) for x in cells):
            continue
        following = [r for r in rows[i+1:i+6] if any(x not in (None,'') for x in r)]
        matching = [r for r in following if len(r) >= len(cells) and all(x in (None,'') for x in r[len(cells):])]
        if not matching:
            continue
        evidence = sum(numeric(x) is not None or is_date(x) for r in matching for x in r[:len(cells)] if x not in (None,''))
        score = len(cells)*3 + evidence + len(matching) - i*.01
        choices.append((score,i,len(cells)))
    if not choices:
        raise InputError('I could not identify a table with a header and data records. Please export a rectangular table with named fields.', 'clarification_required')
    _, offset, width = max(choices)
    return offset, width


def read_tables(name, raw):
    suffix = Path(name).suffix.lower()
    if suffix == '.csv':
        try:
            text = raw.decode('utf-8-sig')
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t|')
            except csv.Error:
                candidates = []
                for delimiter in [",", ";", "\t", "|"]:
                    widths = Counter(len(r) for r in csv.reader(io.StringIO("\n".join(text.splitlines()[:75])),delimiter=delimiter) if 1<len(r)<=MAX_COLUMNS)
                    score = max((width*count for width,count in widths.items()),default=0)
                    candidates.append((score,delimiter))
                delimiter = max(candidates)[1] if max(candidates)[0] else ","
                dialect = type("DetectedDialect",(csv.excel,),{"delimiter":delimiter})
            rows = []
            for row in csv.reader(io.StringIO(text), dialect=dialect, strict=True):
                if len(rows) >= MAX_ROWS+50 or len(row)>MAX_COLUMNS:
                    raise InputError('Dataset exceeds 100,000 records or 100 fields.', 'upload_limit')
                rows.append(row)
            return {None:rows}
        except (UnicodeError,csv.Error) as exc:
            raise InputError('CSV must contain valid UTF-8 table records.') from exc
    if suffix != '.xlsx':
        raise InputError('Supported formats are CSV and XLSX.', 'unsupported_format')
    import openpyxl
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(x.file_size for x in archive.infolist())>50*1024*1024 or len(archive.infolist())>1000:
                raise InputError('Expanded workbook exceeds 50 MiB.', 'upload_limit')
        book = openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
        tables = {}
        cells = 0
        try:
            for ws in book.worksheets:
                if (ws.max_column or 0)>MAX_COLUMNS or (ws.max_row or 0)>MAX_ROWS+50:
                    raise InputError('Workbook exceeds the supported table dimensions.', 'upload_limit')
                rows = []
                for record in ws.iter_rows():
                    row = []
                    for cell in record:
                        if cell.data_type == 'f':
                            raise InputError('Export workbook formulas as values before uploading.', 'formulas_unsupported')
                        row.append(cell.value)
                    cells += len(row)
                    if cells>MAX_CELLS:
                        raise InputError('Workbook exceeds one million cells.', 'upload_limit')
                    rows.append(row)
                tables[ws.title] = rows
            return tables
        finally:
            book.close()
    except (zipfile.BadZipFile,OSError,KeyError) as exc:
        raise InputError('This is not a readable XLSX workbook.') from exc


def parse_table(name: str, raw: bytes, sheet: str | None = None, header_row: int | None = None, business_context: str = ""):
    if not raw or len(raw)>MAX_BYTES:
        raise InputError('Choose a nonempty CSV or XLSX up to 10 MiB.', 'upload_limit')
    if header_row is not None and (not isinstance(header_row,int) or not 1<=header_row<=50):
        raise InputError('Header row must be between 1 and 50.')
    tables = read_tables(name,raw)
    candidates = []
    for title, rows in tables.items():
        if sheet is not None and title != sheet:
            continue
        try:
            offset,width = header_candidate(rows) if header_row is None else (header_row-1,len(rows[header_row-1]))
        except (InputError,IndexError):
            continue
        count = sum(any(v not in (None,'') for v in r) for r in rows[offset+1:])
        candidates.append((count*width,title,offset,width))
    if not candidates:
        raise InputError('I could not find a usable data table. Please provide a table export with records beneath its header.', 'clarification_required')
    matched = [c for c in candidates if c[1] and str(c[1]).casefold() in business_context.casefold()]
    if len(matched)==1:
        candidates = matched
    candidates.sort(key=lambda c:c[0],reverse=True)
    if len(candidates)>1 and candidates[0][0] < 2*candidates[1][0]:
        names = [str(c[1]) for c in candidates[:5]]
        raise InputError('This workbook contains several comparable data tables: '+', '.join(names)+'. Which business dataset should I analyze?', 'clarification_required', {'tables':names})
    _,selected_sheet,offset,width = candidates[0]
    source = tables[selected_sheet]
    headers = [str(h).strip() if h is not None else '' for h in source[offset][:width]]
    if not headers or any(not h or len(h)>100 for h in headers) or len(set(h.casefold() for h in headers)) != len(headers):
        raise InputError('The data header must contain unique, nonempty names up to 100 characters.')
    values = []
    for row in source[offset+1:]:
        if not any(v not in (None,'') for v in row):
            continue
        if len(row)<width or any(v not in (None,'') for v in row[width:]):
            raise InputError('Every data record must match the header field count.')
        values.append(row[:width])
        if len(values)>MAX_ROWS or len(values)*width>MAX_CELLS:
            raise InputError('Dataset exceeds 100,000 records or one million cells.', 'upload_limit')
    if not values:
        raise InputError('The data table has no records.')
    arrays, fields, warnings = [],[],[]
    for i,field in enumerate(headers):
        vals = [None if row[i] in ('',None) else row[i] for row in values]
        present = [v for v in vals if v is not None]
        identifier = bool(re.search(r'(^id$|_id$|code$|zip$|postal)',field,re.I)) or any(re.match(r'^0\d',str(v)) for v in present)
        parsed = [numeric(v) for v in present] if not identifier else []
        units = None
        if present and not identifier and all(v is not None for v in parsed):
            symbols = {v[1] for v in parsed if v[1]}
            if len(symbols)>1 or (symbols and any(v[1] is None for v in parsed)):
                raise InputError(f'{field} mixes incompatible units or number formats.', 'clarification_required')
            units = next(iter(symbols),None)
            array = pa.array([numeric(v)[0] if v is not None else None for v in vals],type=pa.float64())
            role = 'measure'
        elif present and all(is_date(v) for v in present):
            try:
                array = pa.array([dt.date.fromisoformat(str(v)[:10]) if v is not None else None for v in vals],type=pa.date32())
            except ValueError as exc:
                raise InputError(f'{field} contains invalid dates.') from exc
            role = 'time'
        elif present and all(re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',str(v)) for v in present):
            first = any(int(str(v).split('/')[0])>12 for v in present)
            second = any(int(str(v).split('/')[1])>12 for v in present)
            if first == second and "day/month/year" in business_context.casefold():
                first,second = True,False
            elif first == second and "month/day/year" in business_context.casefold():
                first,second = False,True
            if first == second:
                raise InputError('Are the slash-formatted dates day/month/year or month/day/year? Please provide an ISO-date export if both formats are plausible.', 'clarification_required')
            fmt = '%d/%m/%Y' if first else '%m/%d/%Y'
            try:
                array = pa.array([dt.datetime.strptime(str(v),fmt).date() if v is not None else None for v in vals],type=pa.date32())
            except ValueError as exc:
                raise InputError('The data has inconsistent date formats.') from exc
            warnings.append('Date order inferred from unambiguous observed dates.')
            role = 'time'
        else:
            array = pa.array([str(v) if v is not None else None for v in vals],type=pa.string())
            role = 'identifier' if identifier else 'category'
        arrays.append(array)
        field_profile = {'name':field,'type':str(array.type),'missing':array.null_count,'role':role,'units':units,'distinct':len(set(present))}
        if role in {'measure','time'}:
            actual = [v for v in array.to_pylist() if v is not None]
            field_profile.update(min=str(min(actual)) if role=='time' else min(actual),max=str(max(actual)) if role=='time' else max(actual))
        fields.append(field_profile)
    table = pa.Table.from_arrays(arrays,names=headers)
    duplicate_count = len(values)-len({tuple(str(v) for v in row) for row in values})
    profile = {'rows':table.num_rows,'columns':fields,'sheet':selected_sheet,'header_row':offset+1,'duplicates':duplicate_count,
               'preparation':'automatic-v2','warnings':warnings+['Calendar-month aggregation; inferred business meaning is recorded in the analysis plan.']}
    return table,profile


def write_parquet(table,path):
    pq.write_table(table,path,compression='zstd')
