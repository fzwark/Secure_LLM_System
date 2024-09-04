from cores.utils import *

class Executor:
    def __init__(self, llm, label, sys_prompt=None):
        self.llm = llm
        self.sys = sys_prompt
        if self.sys == None:
            self.sys = "You are a helpful assistant."

        if label == None:
            self.label = 'T'
        else:
            self.label = label
        
        if ("gemini" in llm.model) or ("claude" in llm.model):
            self.template = self.sys + "\n"
        else:
            self.template = [
                {"role": "system", "content": self.sys},
                {"role": "user", "content": "{input}"}
            ]


    def get_label(self):
        return self.label

    def execute(self, context):
        '''
        hybird executor
        '''
        # obtain the object
        object = context["Object"] 
        indication = 1
        if object == "LLM":

            if ("gemini" in self.llm.model) or ("claude" in self.llm.model):
                self.template = self.template + context["Instruction"] + "\n" + str(context["Data_input"])
            else:
                self.template[1]["content"] = context["Instruction"] + "\n"
                self.template[1]["content"] += str(context["Data_input"])

            try:
                ret = self.llm.run_one_message(self.template)
            except:
                ret = f"Error in LLM generation process."
                indication = 0
    
        else:
            
            tool = context["Object"]
            function = context["Object_name"]
            tool_type = context["Object_type"]
            if context["Data_input_type"] == "func_none":
                args = None
            else:
                args =  context["Data_input"]["args"]
            
            try:
                if tool_type == 1:
                    if args == None:
                        ret = tool()
                    else:
                        ret = tool(**args)
                else:
                    if args == None:
                        ret = tool(**{'tool_input' : {}})
                    else:
                        ret = tool(**{'tool_input': args})
                    
            except:
                ret = f"ERROR: in execution of {function}."
                indication = 0

        return ret, indication

        