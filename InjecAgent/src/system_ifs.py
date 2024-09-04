from utils_ifs import *
from model import *
import time


class Secure_LLM_System:
    def __init__(self, model=None, memory_path="memory/memory.jsonl", users_config = "config/user_config.yaml"):
        if model == None:
            model = 'gpt-3.5-turbo'
            
        if 'gpt' in model:
            self.llm = ChatGPT(model=model)
        elif 'gemini' in model:
            self.llm = Gemini(model=model)
        elif 'claude' in model:
            self.llm = Claude(model=model)

        self.users_config = users_config

        self.memory_path = memory_path

        self.monitor = Monitor(users=self.users_config)
        
        self.cores = {}

        # align with InjecAgent, only run one time
        self.max_iteration = 1


    def get_plan(self, user, query, generated_plan=None, regerate=0, error=None, former_outputs=[]):
        ret = self.cores[user]["planner"].plan(input=query, generated_steps = generated_plan, regerate=regerate, error=error, output=former_outputs)
        return ret

    def run_task(self, user, query, tools=None, runnable_tools=None, simulate_output=None,  previous_steps = None, previous_output = None):

        # prepare context for query
        planner = self.monitor.prepare_context(user, self.llm, planner_label='T', sys_prompt_planner=SYSTEM_PROMPT_TEMPLATE, tools=tools, runnable_tools= runnable_tools)

        cores = {
            "planner" : planner,
        }

        self.cores[user] = cores
        dict_generated_plan = previous_steps
        regerate = 0
        outputs_records = previous_output
        error = None
        iteration = 1
        # execute the query
        while 1:
            if iteration > self.max_iteration:
                break
            iteration += 1


            checked_generated_plan, former_outputs = self.monitor.security_check(user, dict_generated_plan, previous_output)
           

            step = self.get_plan(user, query=query, generated_plan=checked_generated_plan, regerate = regerate, error=error, former_outputs=former_outputs)

            regerate = 0
            error = None
            
            step = step.split("```json")[-1]
            step = step.split("```python")[-1]
            step = step.split("```")[0]
            pos = step.find("{")
            if pos != 0:
                step = step[pos:]

            try:
                pattern = r'\"Data_input\"\s*:\s*null'
                res = re.findall(pattern, step)
                if res != []:
                    step = step.replace(res[0], "\"Data_input\": \"null\"")
                dict_step = eval(step)

            except Exception as e:
                regerate = 1
                error = ["ERROR: " + str(e), step]
                return error
                
            if isinstance(dict_step, str):
                dict_step = eval(dict_step)
                
            print(step)

            if ("End Signal" in step) or ("\"End Signal\"" in step):
                return "Task Complete"


            # check syntax
            typed_step = self.monitor.type_check(user=user, step=dict_step)    
                      
            if "ERROR: " in typed_step and isinstance(typed_step, str):
                regerate = 1
                print(typed_step)
                if dict_step["Object"] == "None" and dict_step["Instruction"] != "End Signal": 
                    error = ["ERROR: You must specify the value of object field!", step]
                else:
                    error = [typed_step, step]

                return error

            # load data for the step
            runtime_step = self.monitor.prepare_data(user=user, step=typed_step, run_time_plan=dict_generated_plan)

            if "ERROR: " in runtime_step and isinstance(runtime_step, str):
                regerate = 1
                print(runtime_step)
                error = [runtime_step, step]
                return error
           
            # execute the step
            # since InjecAgent did not provide any real tools, use simulate response
            output, indication = simulate_output, 1
            

            # security label assign
            # the output from the tools in InjecAgent is deemed as untrusted 
            output_label = []
            if isinstance(output, list):
                for x in output:
                    output_label.append('U')
            else:
                output_label.append('U')

            # add observation in the step 
            post_str_step, post_dict_step, post_runtime_step= self.monitor.modify_step(user=user, str_step_original=dict_step, dict_step_original=dict_step, runtime_step=runtime_step, output_label=output_label, output=output)

            outputs_records.append(
                {
                    "data"  : output,
                    "label" : output_label
                }
            )
            
            dict_generated_plan.append(post_dict_step)
    
        ans = []
        for idx, item in enumerate(dict_generated_plan):
            ans.append([item["Object"], item, outputs_records[idx]])

        return ans

