Add Sthapathi agent with following ability:
- Has ability to identify skill sets required to develop the project on REPO_ROOT.  Understands the project (REPO_ROOT) overall goal and decides which sub-agents are relevant
- Generates a memory for future and updates it
- Identifies which agents are relevant for the project and respond to the run.py to handle the invocation
  - Silpi and Viharapala are always present coding agents. So, orchestrator will invoke these in a workflow.

Update run.py to uptake Sthapathi:
- Invoke Sthapathi on every run and periodically every 30mins
- Run sub-agents identified by Sthapathi after a beads task is done
- 

Add db_supabase agent (folder) with ability to:
1. Read .env to identify required configuration
2. periodically Invoke script to Automatically fetch db schemas and update the schema types in the REPO_ROOT
3. Generate docs about the schema and access policies
4. In future i could add support for different databases that can be connected to remotely.
