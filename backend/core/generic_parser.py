"""
Generic Excel Parser for HLA Studio.
Zero hardcoding of sheet names, header positions, column names, or control numbers.
Discovers workbook structure, sheets, headers, and rows dynamically from the file.
"""

import os
import re
import openpyxl
from typing import Dict, Any, List, Tuple, Optional


def clean_cell_value(val: Any) -> str:
    """Sanitizes cell value into a clean, normalized string."""
    if val is None:
        return ""
    s = str(val).strip()
    # Normalize fancy unicode quotes, dashes, minus signs
    s = s.replace('\u2013', '-').replace('\u2014', '-').replace('\u2212', '-')
    s = s.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    return s


def normalize_header_token(s: str) -> str:
    """Normalizes header string for robust token matching (snake_case identifier)."""
    clean = re.sub(r'[^a-zA-Z0-9]+', '_', str(s).strip().lower()).strip('_')
    return clean


class GenericExcelParser:
    """
    Parses any Excel workbook (.xlsx, .xls) purely based on its structure and content.
    """

    @classmethod
    def detect_header_row(cls, ws, max_scan_rows: int = 15) -> Tuple[Optional[int], Dict[int, str]]:
        """
        Dynamically detects the most likely header row in a worksheet.
        Looks for the row with the highest density of non-empty string cells
        that look like column labels rather than data values.
        """
        max_r = min(ws.max_row or 1, max_scan_rows)
        max_c = ws.max_column or 1

        best_row = None
        best_headers = {}
        max_score = 0

        for r in range(1, max_r + 1):
            row_vals = {}
            for c in range(1, max_c + 1):
                val = clean_cell_value(ws.cell(r, c).value)
                if val:
                    row_vals[c] = val

            if not row_vals:
                continue

            # Calculate header score
            # Higher score for strings, moderate length, non-numeric, distinct values
            score = 0
            for c, val in row_vals.items():
                if len(val) > 0 and len(val) < 80:
                    score += 2
                if not val.replace('.', '', 1).isdigit():
                    score += 1

            # Penalty if all values look like body sentences rather than headers
            avg_len = sum(len(v) for v in row_vals.values()) / len(row_vals)
            if avg_len > 60:
                score -= 2

            if score > max_score and len(row_vals) >= 1:
                # Ensure it's not a single merged title row if subsequent row has multiple headers
                max_score = score
                best_row = r
                best_headers = row_vals

        # If best_row is a single cell title banner (e.g. len == 1) and row+1 has multiple cells, choose row+1
        if best_row and len(best_headers) == 1 and best_row < max_r:
            next_row_vals = {
                c: clean_cell_value(ws.cell(best_row + 1, c).value)
                for c in range(1, max_c + 1)
                if clean_cell_value(ws.cell(best_row + 1, c).value)
            }
            if len(next_row_vals) > 1:
                best_row = best_row + 1
                best_headers = next_row_vals

        return best_row, best_headers

    @classmethod
    def parse_sheet(cls, ws) -> Dict[str, Any]:
        """
        Parses a single worksheet into headers, normalized headers, and structured rows.
        """
        sheet_name = ws.title
        header_row_idx, col_map = cls.detect_header_row(ws)

        if not header_row_idx or not col_map:
            return {
                "sheet_name": sheet_name,
                "header_row_index": None,
                "original_headers": [],
                "normalized_headers": [],
                "header_map": {},
                "rows": [],
                "row_count": 0,
                "is_empty": True
            }

        sorted_cols = sorted(col_map.keys())
        original_headers = [col_map[c] for c in sorted_cols]
        normalized_headers = [normalize_header_token(h) for h in original_headers]
        header_map = {c: {"original": col_map[c], "normalized": normalize_header_token(col_map[c])} for c in sorted_cols}

        rows = []
        max_r = ws.max_row or header_row_idx
        for r in range(header_row_idx + 1, max_r + 1):
            row_dict = {}
            has_data = False
            for c in sorted_cols:
                raw_val = ws.cell(r, c).value
                val = clean_cell_value(raw_val)
                norm_key = header_map[c]["normalized"]
                orig_key = header_map[c]["original"]
                row_dict[norm_key] = val
                row_dict[f"__orig__{orig_key}"] = val
                if val:
                    has_data = True

            if has_data:
                # Add row index for reference
                row_dict["_excel_row_num"] = r
                rows.append(row_dict)

        return {
            "sheet_name": sheet_name,
            "header_row_index": header_row_idx,
            "original_headers": original_headers,
            "normalized_headers": normalized_headers,
            "header_map": header_map,
            "rows": rows,
            "row_count": len(rows),
            "is_empty": len(rows) == 0
        }

    @classmethod
    def parse_workbook(cls, file_path: str) -> Dict[str, Any]:
        """
        Parses an entire workbook dynamically.
        Discovers all sheets, scans all headers, and extracts all rows.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found: {file_path}")

        wb = openpyxl.load_workbook(file_path, data_only=True)
        discovered_sheets = {}
        total_rows = 0

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_data = cls.parse_sheet(ws)
            discovered_sheets[sheet_name] = sheet_data
            total_rows += sheet_data["row_count"]

        wb.close()

        return {
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "sheet_names": list(discovered_sheets.keys()),
            "sheet_count": len(discovered_sheets),
            "sheets": discovered_sheets,
            "total_rows_scanned": total_rows
        }
