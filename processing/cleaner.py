import re

class TextCleaner:
    @staticmethod
    def clean_text(text: str) -> str:
        """
        Clean extracted text by removing headers, footers, and normalizing whitespace.
        Preserves simple legal numbering if possible, but mainly focuses on noise reduction.
        """
        # Remove potential page numbers (lone numbers at start/end of lines)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Normalize whitespace (multiple spaces/newlines to single space)
        # Note: We might want to keep some paragraph structure, so we'll be careful.
        # Replacing multiple newlines with a unique marker to preserve paragraphs could be an option,
        # but for simple chunking, normalizing to single spaces is often robust enough 
        # unless semantic structure relies heavily on line breaks.
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    @staticmethod
    def is_header_or_footer(line: str) -> bool:
        """
        Heuristic check if a line looks like a header or footer.
        """
        # Example heuristics: too short, looks like a date, "Page X of Y"
        if len(line.strip()) < 5:
            return True
        if re.search(r'Page\s+\d+', line, re.IGNORECASE):
            return True
        return False
