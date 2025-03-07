import os
import shutil
import secrets  # Bu kısmı eklemeyi unutmayın
from werkzeug.utils import secure_filename
from processors import PDFProcessor
from openai_client import OpenAIClient
import tempfile
from flask import Flask, send_file, request, session, redirect, url_for, flash
import zipfile
import config
from datetime import datetime

class CandidateService:
    def __init__(self):
        self.processor = PDFProcessor('simplified_names.json')
        self.openai_client = OpenAIClient(api_key=config.API_KEY)
        self.selected_candidates = []  # Seçilen adayları burada tutuyoruz
        self.user_file_path = None


    def process_candidates(self, files, job_info, keywords, candidate_count, user):
        candidate_texts = []
        valid_candidates = []
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        self.user_file_path = os.path.join(user['preferred_username'], timestamp)
        
        user_folder = os.path.join('uploads', self.user_file_path)
        pdf_directory = os.path.join(user_folder, 'pdfs')
        text_directory = os.path.join(user_folder, 'texts')
        os.makedirs(pdf_directory, exist_ok=True)
        os.makedirs(text_directory, exist_ok=True)

        # Dosyaları pdf_directory içine kaydetme işlemi
        for idx, pdf_file in enumerate(files, start=1):
            # Geçici dosya oluşturma
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                pdf_file.save(temp_file.name)  # FileStorage nesnesini geçici dosyaya kaydediyoruz
                temp_file_path = temp_file.name  # Geçici dosya yolunu alıyoruz
                
            try:
                # PDF metnini çıkarma
                extracted_text, missing_keywords = self.processor.extract_text(temp_file_path, keywords)
                
                # Dosyayı pdf_directory içinde kalıcı olarak kaydedelim
                pdf_file_name = os.path.join(pdf_directory, f"aday{idx}.pdf")
                shutil.move(temp_file_path, pdf_file_name)  # Geçici dosyayı pdf_directory'ye taşıyoruz

                # Metni kaydetme
                if extracted_text and not missing_keywords:
                    result_file_name = f"aday{idx}.txt"
                    with open(os.path.join(text_directory, result_file_name), "w", encoding="utf-8") as f:
                        f.write(extracted_text)
                    valid_candidates.append((extracted_text, result_file_name))
            finally:
                # Eğer temp_file_path hala varsa ve taşınmamışsa, onu sileriz
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

        if valid_candidates:
            candidate_texts = [text for text, _ in valid_candidates]
            original_names = [name for _, name in valid_candidates]

            for i, name in enumerate(original_names, start=1):
                print(f"Aday {i}: {name}")

        # OpenAI modelini kullanarak en iyi adayları bulma
        best_candidates = self.openai_client.get_best_candidate(candidate_texts, job_info, candidate_count)
        processed_response = self.process_response(best_candidates, original_names)

        # Dönen response'a göre selected_candidates klasörünü oluşturma
        selected_folder = os.path.join(pdf_directory, 'selected_candidates')
        os.makedirs(selected_folder, exist_ok=True)

        # Dosya kopyalamadan önce dosya adlarını ve yollarını loglayalım
        for candidate in self.selected_candidates:
            src_path = os.path.join(pdf_directory, f"{candidate}.pdf")
            dest_path = os.path.join(selected_folder, f"{candidate}.pdf")
            
            print(f"Checking for file: {src_path}")
            if os.path.exists(src_path):
                shutil.copy(src_path, dest_path)
                print(f"PDF copied: {src_path} -> {dest_path}")
            else:
                print(f"PDF not found: {src_path}")

        return processed_response, valid_candidates

    
    def process_response(self, response, original_names):
        isim = "Aday" if "Aday" in response else "Candidate"

        selected_candidates = []
        print("Original Names: ", original_names)
        print("Response: ", response)
        for idx, name in sorted(enumerate(original_names, start=1), key=lambda x: -x[0]):
            if f"{isim} {idx}" in response or f"{isim} [{idx}]" in response:
                spliTxt = name.split('.')[0]
                response = response.replace(f"{isim} {idx}", spliTxt)
                selected_candidates.append(spliTxt)

        self.selected_candidates = selected_candidates
        return response

    
    def allowed_file(self, filename):
        ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def save_file(self, file, filename, pdf_directory):
        # PDF dosyasını kaydetme
        filepath = os.path.join(pdf_directory, filename)
        file.save(filepath)
        return filepath

    def save_anonymized_data(self, idx, extracted_text, filepath, pdf_directory, text_directory):
        valid_candidates = []
        # Anonimleştirilmiş metin dosyasını kaydetme
        text_file = f"aday{idx}.txt"
        with open(os.path.join(text_directory, text_file), "w", encoding="utf-8") as f:
            f.write(extracted_text)

    def zip_selected_pdfs(self):
        directory = self.best_candidates_path()
        # Zip dosyasının yolu
        zip_filename = "selected_candidates.zip"
        zip_filepath = os.path.join(directory, zip_filename)

        # Zip dosyasını oluştur
        with zipfile.ZipFile(zip_filepath, 'w') as zipf:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.pdf'):
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.basename(file_path))

        return zip_filepath
    
    def best_candidates_path(self):
        return os.path.join('uploads', self.user_file_path, 'pdfs', 'selected_candidates')