import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname);
const manifest = JSON.parse(readFileSync(resolve(root, 'scenarios.json'), 'utf8'));
const scenarioIds = new Set();
const personas = new Set(['A', 'B', 'C', 'D', 'E', 'F']);

if (manifest.schema_version !== '1.0' || !Array.isArray(manifest.scenarios)) {
	throw new Error('scenarios.json must use schema 1.0 and contain a scenarios array');
}

for (const scenario of manifest.scenarios) {
	for (const field of ['id', 'title', 'personas', 'priority', 'routes', 'viewports', 'steps', 'expected']) {
		if (scenario[field] === undefined) throw new Error(`${scenario.id || 'scenario'} is missing ${field}`);
	}
	if (!/^[A-Z0-9]+-[0-9]{3}$/.test(scenario.id)) throw new Error(`Invalid scenario id ${scenario.id}`);
	if (scenarioIds.has(scenario.id)) throw new Error(`Duplicate scenario id ${scenario.id}`);
	if (!scenario.personas.length || scenario.personas.some((value) => !personas.has(value))) {
		throw new Error(`${scenario.id} has invalid personas`);
	}
	scenarioIds.add(scenario.id);
}

const referenced = new Set();
for (const filename of readdirSync(resolve(root, 'charters'))) {
	const content = readFileSync(resolve(root, 'charters', filename), 'utf8');
	for (const match of content.matchAll(/\b[A-Z0-9]+-[0-9]{3}\b/g)) referenced.add(match[0]);
}
for (const id of referenced) {
	if (!scenarioIds.has(id)) throw new Error(`Charter references unknown scenario ${id}`);
}

for (const scenario of manifest.scenarios.filter((item) => item.priority === 'critical')) {
	if (!scenario.enabled) throw new Error(`Critical scenario ${scenario.id} is disabled`);
}

JSON.parse(readFileSync(resolve(root, 'schemas', 'finding.schema.json'), 'utf8'));
JSON.parse(readFileSync(resolve(root, 'schemas', 'scenario.schema.json'), 'utf8'));
JSON.parse(readFileSync(resolve(root, 'templates', 'finding.template.json'), 'utf8'));

process.stdout.write(`Validated ${scenarioIds.size} UAT scenarios and ${referenced.size} charter references.\n`);
