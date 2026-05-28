SANDBOX := sandbox
PORT    := 7777

.PHONY: folder serve reset judge-on judge-off install

install:
	pip3 install -r requirements.txt

folder:
	mkdir -p $(SANDBOX)/folder-1 $(SANDBOX)/folder-2 $(SANDBOX)/folder-3
	mkdir -p $(SANDBOX)/do-not-enter $(SANDBOX)/chaos
	@for i in 1 2 3; do \
		printf '# Folder %s\n\nSandboxed content for demo folder %s.\n' $$i $$i \
			> $(SANDBOX)/folder-$$i/README.md; \
		printf '#!/bin/bash\necho "I am a script"\n' \
			> $(SANDBOX)/folder-$$i/script.sh; \
		chmod +x $(SANDBOX)/folder-$$i/script.sh; \
	done
	printf '# Why did you enter?\n' > $(SANDBOX)/do-not-enter/README.md
	touch $(SANDBOX)/chaos/README.md
	@echo "Sandbox ready."

serve:
	@echo "Judge status → http://localhost:$(PORT)"
	JUDGE_PORT=$(PORT) python3 server.py

reset:
	rm -f judge.db journal.jsonl
	@echo "State cleared."

judge-on:
	touch .judge-active
	@echo "Judge is ON  — constitution enforced."

judge-off:
	rm -f .judge-active
	@echo "Judge is OFF — unchecked execution."
