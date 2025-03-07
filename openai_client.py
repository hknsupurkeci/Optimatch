#openai_client
from transformers import GPT2TokenizerFast
from openai import OpenAI
import re

tokenizer = GPT2TokenizerFast.from_pretrained('Xenova/gpt-4o')
class OpenAIClient:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)

    def get_best_candidate(self, candidate_texts, job_info, bestCandidatesCount):
        # Başlangıçta candidate_texts listesini candidate_dict ve reference_dict olarak iki sözlüğe dönüştürüyoruz
        reference_dict = {idx: text for idx, text in enumerate(candidate_texts, start=1)}
        candidate_dict = reference_dict.copy()
        max_tokens = 120000
        print("get_best_candidate_count: ", bestCandidatesCount)
        print("Max token length:", tokenizer.model_max_length)

        while True:
            print(candidate_dict.keys())
            response_idx = []
            # prompt = self.job_prompt()+"\n"
            prompt = f"Job posting information: {job_info}\n\Candidates:\n"
            current_tokens = len(tokenizer.encode(prompt))
            for idx, text in candidate_dict.items():
                candidate_prompt = f"Aday {idx}:\n{text}\n\n"
                new_tokens = len(tokenizer.encode(candidate_prompt))
                if current_tokens + new_tokens > max_tokens:
                    prompt += self.job_prompt(bestCandidatesCount) + "\n"
                    response_idx += self.process_and_extract(prompt)
                    print("Respons: " + str(response_idx)+"\n")
                    prompt = self.create_prompt(candidate_prompt, job_info)
                    current_tokens = len(tokenizer.encode(prompt))
                else:
                    prompt += candidate_prompt
                    current_tokens += new_tokens

            if len(response_idx) == 0:
                    print("break idx: ")
                    break
            else:
                # 
                print("end for: " + str(response_idx) + "\n")
                prompt += self.job_prompt(bestCandidatesCount) + "\n"
                response_idx += self.process_and_extract(prompt)
                print("Respons: " + str(response_idx)+"\n")
                prompt = self.create_prompt(candidate_prompt, job_info)
                current_tokens = len(tokenizer.encode(prompt))
                # id'ler ile yeni bir candidate_dict oluşturulacak
                response_idx = list(dict.fromkeys(response_idx))
                candidate_dict = {idx: reference_dict[idx] for idx in response_idx}
                candidate_dict = {k: candidate_dict[k] for k in sorted(candidate_dict)}
                response_idx = []  

        print("response")
        prompt += self.last_prompt(bestCandidatesCount) + "\n"
        response = self.process_prompt(prompt)
        return response
        

    def create_prompt(self, candidate_prompt, job_info):
        prompt = f"Job posting information: {job_info}\nCandidates:\n"
        prompt += candidate_prompt
        return prompt
    
    def process_and_extract(self, prompt):
        print("istek atıldı: " + prompt)
        response = self.process_prompt(prompt)
        response_idx = self.extract_numbers(response)
        return response_idx

    def process_prompt(self, prompt):
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a recruitment assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=4096,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )
            return response.choices[0].message.content
        except Exception as e:
            print("Hata oluştu:", str(e))
            return "Bir hata oluştu. Lütfen daha sonra tekrar deneyin."
    
    def job_prompt(self, count):
        print("job_prompt ", count)
        return (
            f"Lütfen bir İnsan Kaynakları işe alım uzmanı olarak, adayların **yalnızca özgeçmişlerine dayanarak**, bu iş için en iyi {count} adayı değerlendirin ve sıralayın. "
            "İşle doğrudan ilgili olmayan staj veya benzeri deneyimleri hariç tutun. "
            "Her adayın pozisyona uygunluğunu değerlendirirken, **detaylı açıklamalar yapmayın**.\n\n"
            "İş ilanında listelenen kriterlere odaklanın ve adayların özgeçmişlerinde **açıkça belirtilmeyen hiçbir bilgiyi eklemeyin veya varsaymayın**. "
            "Cevabınızı şu formatta yazın: Aday 1, Aday 2, vb.\n"
            "Cevabınızı Türkçe olarak verin.\n"
        )

    def last_prompt(self, count):
        print("last_prompt ", count)
        return (
            f"Lütfen bir İnsan Kaynakları işe alım uzmanı olarak, bu iş ilanı için en iyi {count} adayı, staj veya benzeri deneyimleri hariç tutarak değerlendirin ve sıralayın.\n"
            "Adayları **yalnızca özgeçmişlerindeki bilgilere dayanarak** objektif ve tarafsız bir şekilde değerlendirin. "
            "**Adayların özgeçmişlerinde bulunmayan hiçbir bilgiyi eklemeyin, varsaymayın veya tahmin etmeyin.**\n"
            "Her adayın seçilme nedenine dair **ayrıntılı** bir özet sağlayın; bu özet, iş gereksinimleriyle eşleşen nitelik ve deneyimlerin yanı sıra, adayların özgeçmişlerinde belirtilen diğer ilgili becerileri, başarıları ve deneyimleri de içermelidir. "
            "Adayların pozisyona katkı sağlayabilecek tüm önemli özelliklerini vurgulayın.\n"
            "Her adayın kimlik numarasını yalnızca bir kez 'Aday [id]:' formatında gösterin.\n"
            f"Size gönderdiğimiz en iyi {count} adayın özellikleri ve neden onları seçmemiz gerektiği konusunda **detaylı bir açıklama** yazın. "
            "Adayların sonuçlarında aradığımız kriterleri **tekrarlamayın veya belirtmeyin**, ancak adayların bu kriterlere nasıl uyduklarını ve ek olarak hangi özelliklere sahip olduklarını açıklayın.\n"
            "Cevabınızı şu formatta yazın:\n\n"
            "Aday [id]:\n"
            "- Adayın ilgili deneyimleri ve niteliklerinin detaylı özeti.\n\n"
            "* Lütfen cevabınızı Türkçe olarak verin."
        )


    def extract_numbers(self, data):
        # Regex ile 'Aday' kelimesinden sonra gelen sayıları buluyoruz.
        # '\d+' ifadesi bir veya daha fazla rakamı ifade eder.
        numbers = re.findall(r'Aday (\d+)', data)
        # Bulunan sayıları integer listesi olarak döndürüyoruz.
        return [int(num) for num in numbers]
