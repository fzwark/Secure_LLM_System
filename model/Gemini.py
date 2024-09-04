import os
import yaml
import google.generativeai as genai



class Gemini:
    def __init__(self, model=""):
        self.models = ['gemini-1.5-pro']
        
        if model == "":
            self.model = self.models[0]
        
        elif model not in self.models:
            raise Exception("Undefined model.")
        
        else:
            self.model = model


        config_path = os.path.join("config/gemini.yaml")

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.config = config

        genai.configure(api_key=self.config['api_key'])
        
        self.gen_model = genai.GenerativeModel(self.model)

    def run(self, messages):
        
        ans = self.gen_model.generate_content(
            messages,
            generation_config=genai.types.GenerationConfig(
            # Only one candidate for now.
            candidate_count=1,
            max_output_tokens=200,
            temperature=self.config["temperature"]
            )
        )

        if ans == None:
            raise Exception("Gemini ret error.")

        output = ans.text

        return output
    
    def run_one_message(self, sys, input):
        messages = "System Prompt:\n" + sys + "\n\n\n" + input
        output = self.run(messages)
        return output