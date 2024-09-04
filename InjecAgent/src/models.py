import os
from src.utils import get_response_text
import time, yaml
import google.generativeai as genai

class BaseModel:
    def __init__(self):
        self.model = None

    def prepare_input(self, sys_prompt,  user_prompt_filled):
        raise NotImplementedError("This method should be overridden by subclasses.")

    def call_model(self, model_input):
        raise NotImplementedError("This method should be overridden by subclasses.")
    
class ClaudeModel(BaseModel):     
    def __init__(self, params):
        super().__init__()  
        from anthropic import Anthropic
        with open("config/claude.yaml", "r") as f:
            api_key = yaml.safe_load(f)['api_key']

        os.environ["ANTHROPIC_API_KEY"] = api_key

        self.anthropic = Anthropic(
            api_key= os.environ.get("ANTHROPIC_API_KEY"),
        )
        self.params = params

    def prepare_input(self, sys_prompt, user_prompt_filled):
        model_input = f"{sys_prompt} {user_prompt_filled}"
        return model_input

    def call_model(self, model_input):
        ans = self.anthropic.messages.create(
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": model_input,
                    }
                ],
                temperature = 0,
                model=self.params['model_name'],
            )

        if ans == None:
            raise Exception("Claude ret error.")
    
        output = ans.content[0].text
        
        return output


class GeminiModel(BaseModel):     
    def __init__(self, params):
        super().__init__()  
        with open("config/gemini.yaml", "r") as f:
            api_key = yaml.safe_load(f)['api_key']

        genai.configure(api_key=api_key)

        self.params = params
        self.gen_model = genai.GenerativeModel(self.params['model_name'])

    def prepare_input(self, sys_prompt, user_prompt_filled):
        model_input = f"{sys_prompt} {user_prompt_filled}"
        return model_input

    def call_model(self, model_input):    
        ans = self.gen_model.generate_content(
                model_input,
                generation_config=genai.types.GenerationConfig(
                # Only one candidate for now.
                candidate_count=1,
                max_output_tokens=4096,
                temperature=0
                ),
                safety_settings= [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE",
                    },
                ]
        )

        if ans == None:
            raise Exception("Gemini ret error.")

        output = ans.text

        return output
    
class GPTModel(BaseModel):
    def __init__(self, params):
        super().__init__()  
        from openai import OpenAI
        self.client = OpenAI(
            api_key = os.environ.get("OPENAI_API_KEY"),
            organization = os.environ.get("OPENAI_ORGANIZATION")
        )
        self.params = params

    def prepare_input(self, sys_prompt, user_prompt_filled):
        model_input = [
            {"role": "system", "content":sys_prompt},
            {"role": "user", "content": user_prompt_filled}
        ]
        return model_input

    def call_model(self, model_input):
        completion = self.client.chat.completions.create(
            model=self.params['model_name'],
            messages=model_input,
            temperature=0
        )
        return completion.choices[0].message.content
    
import together   
class TogetherAIModel(BaseModel): 
    def __init__(self, params):
        super().__init__()  
        
        from src.prompts.prompt_template import PROMPT_TEMPLATE
        
        self.params = params
        self.model = self.params['model_name']
        self.prompt = PROMPT_TEMPLATE[self.model]

    def prepare_input(self, sys_prompt, user_prompt_filled):
        model_input = self.prompt.format(sys_prompt = sys_prompt, user_prompt = user_prompt_filled)
        return model_input
    
    def call_model(self, model_input, retries=3, delay=2, max_tokens =512):
        attempt = 0
        while attempt < retries:
            try:
                completion = together.Complete.create(
                    model=self.model,
                    prompt=model_input,
                    max_tokens=max_tokens,
                    temperature=0
                )
                return completion['choices'][0]['text']
            except Exception as e:
                attempt += 1
                max_tokens = max_tokens // 2
                print(f"Attempt {attempt}: An error occurred - {e}")
                if attempt < retries:
                    time.sleep(delay)  # Wait for a few seconds before retrying
                else:
                    return ""
    
class LlamaModel(BaseModel):     
    def __init__(self, params):
        super().__init__()  
        import transformers
        import torch
        tokenizer = transformers.AutoTokenizer.from_pretrained(params['model_name'])
        self.pipeline = transformers.pipeline(
            "text-generation",
            model=params['model_name'],
            tokenizer=tokenizer,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            max_length=4096,
            do_sample=False, # temperature=0
            eos_token_id=tokenizer.eos_token_id,
        )

    def prepare_input(self, sys_prompt, user_prompt_filled):
        model_input = f"[INST] <<SYS>>\n{sys_prompt}\n<</SYS>>\n\n{user_prompt_filled} [/INST]"
        return model_input

    def call_model(self, model_input):
        output = self.pipeline(model_input)
        return get_response_text(output, "[/INST]")
    
MODELS = {
    "Claude": ClaudeModel,
    "GPT": GPTModel,
    "Llama": LlamaModel,
    "TogetherAI": TogetherAIModel,
    "Gemini" : GeminiModel
}   