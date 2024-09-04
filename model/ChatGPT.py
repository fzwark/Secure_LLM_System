from openai import OpenAI
import os
import yaml


class ChatGPT:
    def __init__(self, model=""):
        self.models = ['gpt-3.5-turbo', 'gpt-4-turbo', 'gpt-4o']
        
        if model == "":
            self.model = self.models[0]
        
        elif model not in self.models:
            raise Exception("Undefined model.")
        
        else:
            self.model = model

        config_path = os.path.join("config/gpt.yaml")

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.config = config

        self.client = OpenAI(
            # This is the default and can be omitted
            # api_key=os.environ.get("OPENAI_API_KEY"),
            api_key=self.config['api_key']
        )

        self.template = [
            {"role": "system", "content": "{sys}"},
            {"role": "user", "content": "{input}"}
        ]


    def run(self, messages):
        temperature = self.config["temperature"]

        ans = self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature = temperature,
            max_tokens=400,
        )

        if ans == None:
            raise Exception("Chatgpt ret error.")

        output = ans.choices[0].message.content
        return output

    def run_one_message(self, sys, input):
        # prepare the input to the LLM
        self.template[0]["content"] = sys
        self.template[1]["content"] = input
        messages = self.template
        output = self.run(messages)
        return output