from cores.utils import *

class Planner:
    def __init__(self, llm=None, sys_prompt=None, label= None):
        '''
        initialize the the planner
        '''
        if llm == None:
            raise Exception("Empty LLM")
        
        if sys_prompt == None:
            raise Exception("Empty system prompt")
        
        if label == None:
            self.label = 'T'
        else:
            self.label = label
        
        self.sys = sys_prompt
        self.llm = llm


    def get_label(self):
        return self.label
    
    def plan(self, input = None, generated_steps=None, regerate=0, error=None, output=None):
        if input == None:
            raise Exception("Empty input")

        if regerate:
            input = f"User query:\n\n{input}\n\nThe given generated plan is:\n{generated_steps}\n\nThe outputs from previous steps are as follows:\n{output}\n\nThe last step you generated is wrong:\n{error[1]}\n\nThe error is {error[0]}\n\nPlease regenerate it:\n"
        else:
            input = f"User query:\n\n{input}\n\nThe given generated plan is:\n{generated_steps}\n\nThe outputs from previous steps are as follows:\n{output}\n\nBased on the abve information, the next step should be:\n"
        
        ret = self.llm.run_one_message(self.sys, input)
        return ret