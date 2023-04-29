# parapyats
This is my 2nd attempt to restructure a router testing framework built on pyats and a proprietary framework.  
The design principles are:  
(1) Maximize reuse of proprietary framework: test execution structure, logging structure, and router prompts' automatic reply are kept.  
(2) Simplicity: all the macro data such as testbed structure are stored in a singleton-facade architecture.  
(3) Ease of use: common features like executing a command and applying the proper parser are grouped in the same function.  
(4) Execution security: paired steps are presented as decorators. For example, "switch to router B, execute these commands, then switch back to router A!" is presented as a try_to_execute_commands_on_router_B decorator.  
(5) Comprehensive logging: when executing commands like "count all lines that match certain criteria," the full output is first acquired before the command is rerun with the criteria and "utility wc -l" to isolate the line count.  
(6) Decent execution speed and stability: each waiting period is fine-tuned for the task.  

## architectural pattern:  
parapyats  
&nbsp;&nbsp;&nbsp;&nbsp;\|  
&nbsp;&nbsp;&nbsp;&nbsp;\`------> pfc_parapyats  ------> pfc_test  
&nbsp;&nbsp;&nbsp;&nbsp;\|  
&nbsp;&nbsp;&nbsp;&nbsp;\`------> bgp_parapyats  ------> bgp_test  
&nbsp;&nbsp;&nbsp;&nbsp;\|  
&nbsp;&nbsp;&nbsp;&nbsp;\`------> ecmp_parapyats ------> ecmp_test  
  
Parapyats defines the core functions, including start_step(), troubleshootable_step(), run_on_router(), run_cmds(), configure(), start_ixia_traffic(), and count_lines().  
Each feature-specific test has its own parapyats extension. In the example provided, ECMP test has its own ecmp_parapyats library, which contains many functions used in ecmp_test's start_step() function.  
Each feature-specific test also has its own yaml file, which is not included.  

## Downsides:  
(1) Funky code reusability: multiple inheritance is needed if a test is designed that requires functions from two feature-specific parapyats files.  
(2) Architectural flaws: this system does not follow OOP-based design patterns. It combines pyats-related frameworks and logging, ssh sessions, traffic generator control, and troubleshooting code generator into one big class. (To be fair, I was working with a lot of limitations due to existing frameworks.) This needs to be refactored for easier feature development (especially for the troubleshooter) and manageability.  
(3) Many one-time functions: start_step() was designed to eliminate redundant try-except statements and reduce indentations. However, I have so far failed to feed multiple statements into start_step() without passing them in as a function. Therefore, many functions are created for one-time use.  

Because of these flaws, I am now developing classemulator (https://github.com/hyv3m1nd/classemulator), my 3rd attempt at refactoring our testing framework.
