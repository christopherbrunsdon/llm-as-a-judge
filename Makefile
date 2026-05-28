SANDBOX := sandbox
PORT    := 7777

.PHONY: folder serve reset soft-reset judge-on judge-off clown-on clown-off install test-server logs assets

install:
	pip3 install --break-system-packages -r requirements.txt

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
	rm -f judge.db journal.jsonl .judge-active .clown-active
	@echo "State cleared. Judge is OFF."

soft-reset:
	rm -f .judge-active .clown-active
	$(MAKE) folder
	@echo "Sandbox reseeded. DB and journal preserved. Judge is OFF."

test-server:
	@python3 test_server.py

judge-on:
	touch .judge-active
	@echo "Judge is ON  — constitution enforced."

judge-off:
	rm -f .judge-active
	@echo "Judge is OFF — unchecked execution."

clown-on:
	touch .clown-active
	@echo "Clown is ON  — chaos agent loaded."

clown-off:
	rm -f .clown-active
	@echo "Clown is OFF."

logs:
	@touch journal.jsonl
	@tail -f journal.jsonl | python3 tail_logs.py

assets:
	mkdir -p assets
	cp /System/Library/Sounds/Ping.aiff assets/ping.aiff
	@echo "Assets ready."
