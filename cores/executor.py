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
           input = context["Instruction"] + "\n" + str(context["Data_input"])
            try:
                ret = self.llm.run_one_message(self.sys, input)
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

        
