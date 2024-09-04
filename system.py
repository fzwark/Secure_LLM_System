from security_module import *
from model import *
import time


class Secure_LLM_System:
    def __init__(self, model=None, tools_check=None, tools_config=None, memory_path="memory/memory.jsonl", users_config = "config/user_config.yaml"):
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

        self.monitor = Monitor(users=self.users_config, tools_check = tools_check, tools_config = tools_config)
        
        self.cores = {}

        self.max_iteration = 15


    def get_plan(self, user, query, generated_plan=None, regerate=0, error=None, former_outputs=[]):
        ret = self.cores[user]["planner"].plan(input=query, generated_steps = generated_plan, regerate=regerate, error=error, output=former_outputs)
        return ret

    def run_task(self, user, query, tools=None, runnable_tools=None):

        # prepare context for query
        planner, executor = self.monitor.prepare_context(user, self.llm, planner_label='T', sys_prompt_planner=SYSTEM_PROMPT_TEMPLATE, sys_prompt_executor=None, tools=tools, runnable_tools= runnable_tools)

        cores = {
            "planner" : planner,
            "executor" : executor
        }

        self.cores[user] = cores

        str_generated_plan = []
        dict_generated_plan = []
        runtime_plan = []
        generation_time_list = []
        execution_time_list = []
        check_time_list = []
        modify_time_list = []
        regerate = 0
        outputs_records = []
        error = None
        iteration = 0

        # execute the query
        while 1:
            if iteration > self.max_iteration:
                break
            iteration += 1

            security_start = time.time()
            checked_generated_plan, former_outputs = self.monitor.security_check(user, dict_generated_plan)
            security_end = time.time()
            
            step_start = time.time()
            step = self.get_plan(user, query=query, generated_plan=checked_generated_plan, regerate = regerate, error=error, former_outputs=former_outputs)
            end = time.time()

            regerate = 0
            error = None
            
            generation_time = end-step_start
            generation_time_list.append(generation_time)

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
                error = [e, step]
                print(e)
                continue
                
            if isinstance(dict_step, str):
                dict_step = eval(dict_step)
                
            print(step)

            if ("End Signal" in step) or ("\"End Signal\"" in step):
                break


            # check syntax
            typed_step = self.monitor.type_check(user=user, step=dict_step)    
                      
            if "ERROR: " in typed_step and isinstance(typed_step, str):
                regerate = 1
                print(typed_step)
                if dict_step["Object"] == "None" and dict_step["Instruction"] != "End Signal": 
                    error = ["You must specify the value of object field!", step]
                else:
                    error = [typed_step, step]
                continue

            # load data for the step
            runtime_step = self.monitor.prepare_data(user=user, step=typed_step, run_time_plan=runtime_plan)

            if "ERROR: " in runtime_step and isinstance(runtime_step, str):
                regerate = 1
                print(runtime_step)
                error = [runtime_step, step]
                continue

            end1 = time.time()
            type_check_time = end1-end
            check_time_list.append(type_check_time + security_end - security_start)            
            
            # execute the step
            output, indication = self.cores[user]["executor"].execute(context=runtime_step)

            if indication == 0:
                regerate = 1
                error = [output, step]
                print(output)
                continue
            
            end2 = time.time()
            execution_time = end2-end1
            execution_time_list.append(execution_time)

            # security label assign
            output_label = self.monitor.post_security_label_assign(output=output, step=runtime_step, user=user)
            # add observation in the step 
            post_str_step, post_dict_step, post_runtime_step= self.monitor.modify_step(user=user, str_step_original=dict_step, dict_step_original=dict_step, runtime_step=runtime_step, output_label=output_label, output=output)

            outputs_records.append(
                {
                    "data"  : output,
                    "label" : output_label
                }
            )

            str_generated_plan.append(json.dumps(post_str_step, indent=4))
            dict_generated_plan.append(post_dict_step)

            step_end = time.time()
            modify_time = step_end-end2
            modify_time_list.append(modify_time)

            runtime_plan.append(post_runtime_step)

        
        ans = []
        for idx, item in enumerate(runtime_plan):
            ans.append([item["Object_name"], outputs_records[idx]['data']])

        # store into memory
        log = {
            "query" : query,
            "user" : user,
            "model" : self.llm.model,
            "time" : time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "execution_trace" : dict_generated_plan,
            "output_trace" : outputs_records
        }

        with open(self.memory_path, "a") as f:
            json.dump(log, f)

        return ans, outputs_records[-1]['data'], [generation_time_list, check_time_list, execution_time_list, modify_time_list]  

