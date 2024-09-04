import os
import yaml, time
import anthropic


class Claude:
    def __init__(self, model=""):
        self.models = ['claude-3-5-sonnet-20240620']
        
        if model == "":
            self.model = self.models[0]
        
        elif model not in self.models:
            raise Exception("Undefined model.")
        
        else:
            self.model = model
        
        config_path = os.path.join("config/claude.yaml")

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.config = config

        self.client = anthropic.Anthropic(
            api_key=self.config['api_key'],

        )

    

    def run(self, messages):
        
        ans = self.client.messages.create(
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": messages,
                }
            ],
            temperature = self.config['temperature'],
            model=self.model,
        )

        if ans == None:
            raise Exception("Claude ret error.")
    
        output = ans.content[0].text

        return output

    def run_one_message(self, sys, input):
        messages = "System Prompt:\n" + sys + "\n\n\n" + input
        output = self.run(messages)
        return output