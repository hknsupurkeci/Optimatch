import PyPDF2
import re
import json
import logging
from docx import Document  # python-docx modülü


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self, json_file_path):
        # JSON dosyasını yükle
        with open(json_file_path, 'r', encoding='utf-8') as file:
            self.names_data = json.load(file)

    @staticmethod
    def clean_text(text):
        # Harf ve sayı kombinasyonlarını ayır
        text = re.sub(r'(\d)([a-zA-Z])|([a-zA-Z])(\d)', r'\1\3 \2\4', text)
        # Küçük harf ve ardından büyük harf geliyorsa ayır
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # Fazladan boşlukları temizle ve metni döndür
        clean_text = re.sub(r'\s+', ' ', text).strip()
        return clean_text

    def is_turkish_name(self, word):
        # Check if the word is a Turkish name using the loaded JSON data
        word_lower = word.lower()  # Kelimeyi küçük harfe çevir
        return word_lower in self.names_data

    def anonymize_text(self, text):
        # Regex desenleri
        tc_regex = r'\b\d{11}\b'
        phone_regex = r'\b(\+?\d{1,3})?(\s?\(?\d{3}\)?\s?\d{3}\s?\d{2}\s?\d{2})\b|\b\d{10}\b'
        email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        url_regex = r'\b(?:http|https|www)?://[^\s]+|(?<!@)(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?=\s|$)|\b[a-zA-Z0-9-]+\.[a-zA-Z]{2,}/[a-zA-Z0-9-]+\b'
        date_regex = r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'

        # İsim ve soyisim anonimleştirme
        def replace_name(word):
            if self.is_turkish_name(word):
                return word[0]+word[1]+"***"
            return word

        words = text.split()
        anonymized_words = [replace_name(word) for word in words]
        anonymized_text = ' '.join(anonymized_words)

        # Regex ile anonimleştirme işlemleri
        anonymized_text = re.sub(tc_regex, 'TC_KİMLİK', anonymized_text)
        anonymized_text = re.sub(phone_regex, 'PHONE', anonymized_text)
        anonymized_text = re.sub(email_regex, 'EMAIL', anonymized_text)
        anonymized_text = re.sub(url_regex, 'URL', anonymized_text)
        anonymized_text = re.sub(date_regex, 'DATE', anonymized_text)

        return anonymized_text
    
    def extract_text(self, file_path, keywords):
        try:
            # Yalnızca PDF dosyalarını işle
            if file_path.lower().endswith('.pdf'):
                return self.extract_pdf_text(file_path, keywords)
            else:
                logger.info(f"Skipping unsupported file type: {file_path}")
                return None, []
        except Exception as e:
            logger.error(f"Dosya işlenemedi: {file_path}, Hata: {e}")
            return None, []  # Hatalı dosya durumunda None döndür
        
    def extract_pdf_text(self, pdf_file, keywords):
        extracted_text = ""
        missing_keywords = set(keywords)

        try:
            with open(pdf_file, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                total_pages = len(reader.pages)
                
                # Maksimum 10 sayfa ile sınırla
                max_pages = min(total_pages, 10)

                for page_num in range(max_pages):
                    try:
                        page = reader.pages[page_num]
                        text = page.extract_text() if page.extract_text() else ""
                        clean_text = self.clean_text(text)
                        anonymized_text = self.anonymize_text(clean_text) #clean_Text
                        extracted_text += anonymized_text + "\n"

                        # Anahtar kelimeleri kontrol et
                        for keyword in keywords:
                            if keyword.lower() in anonymized_text.lower():
                                missing_keywords.discard(keyword)
                    except Exception as e:
                        logger.warning(f"Sayfa işlenemedi (Sayfa: {page_num}, PDF: {pdf_file}): {e}")

        except Exception as e:
            logger.error(f"PDF okunamadı veya işlenemedi: {pdf_file}, Hata: {e}")
            return "", keywords  # PDF işlenemediğinde boş metin ve tüm anahtar kelimeleri döndür

        # Metni belirli bir satır uzunluğuna böl
        extracted_text = self.split_into_lines(extracted_text, 50)
        return extracted_text, list(missing_keywords)

    
    @staticmethod
    def split_into_lines(text, words_per_line):
        words = text.split()
        lines = [' '.join(words[i:i + words_per_line]) for i in range(0, len(words), words_per_line)]
        return '\n'.join(lines)
