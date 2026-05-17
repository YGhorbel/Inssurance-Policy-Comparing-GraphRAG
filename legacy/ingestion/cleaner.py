import re

class TextCleaner:
    @staticmethod
    def clean_text(text: str) -> str:
        """
        Clean extracted text by removing headers, footers, and normalizing whitespace.
        """
        # Remove potential page numbers (lone numbers at start/end of lines)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Normalize whitespace (multiple spaces/newlines to single space)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
