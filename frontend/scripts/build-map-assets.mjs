import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sourceDir = resolve(root, 'map-source');
const outputDir = resolve(root, 'static', 'geo');

const countryTolerance = Number(process.env.COUNTRY_TOLERANCE || 0.015);
const subdivisionTolerance = Number(process.env.SUBDIVISION_TOLERANCE || 0.002);
const lakeTolerance = Number(process.env.LAKE_TOLERANCE || 0.006);

const readJson = async (name) => JSON.parse(await readFile(resolve(sourceDir, name), 'utf8'));
const round = (value) => Math.round(value * 100000) / 100000;

function squaredDistance(a, b) {
	const x = a[0] - b[0];
	const y = a[1] - b[1];
	return x * x + y * y;
}

function squaredSegmentDistance(point, start, end) {
	let x = start[0];
	let y = start[1];
	let dx = end[0] - x;
	let dy = end[1] - y;
	if (dx !== 0 || dy !== 0) {
		const position = ((point[0] - x) * dx + (point[1] - y) * dy) / (dx * dx + dy * dy);
		if (position > 1) {
			x = end[0];
			y = end[1];
		} else if (position > 0) {
			x += dx * position;
			y += dy * position;
		}
	}
	dx = point[0] - x;
	dy = point[1] - y;
	return dx * dx + dy * dy;
}

function simplifyRadial(points, toleranceSquared) {
	let previous = points[0];
	const output = [previous];
	for (let index = 1; index < points.length; index += 1) {
		const point = points[index];
		if (squaredDistance(point, previous) > toleranceSquared) {
			output.push(point);
			previous = point;
		}
	}
	if (previous !== points.at(-1)) output.push(points.at(-1));
	return output;
}

function simplifyDouglasPeucker(points, toleranceSquared) {
	const markers = new Uint8Array(points.length);
	const stack = [0, points.length - 1];
	markers[0] = markers[points.length - 1] = 1;
	while (stack.length) {
		const last = stack.pop();
		const first = stack.pop();
		let maxDistance = 0;
		let split = 0;
		for (let index = first + 1; index < last; index += 1) {
			const distance = squaredSegmentDistance(points[index], points[first], points[last]);
			if (distance > maxDistance) {
				split = index;
				maxDistance = distance;
			}
		}
		if (maxDistance > toleranceSquared) {
			markers[split] = 1;
			stack.push(first, split, split, last);
		}
	}
	return points.filter((_, index) => markers[index]);
}

function simplifyRing(ring, tolerance) {
	if (!ring?.length) return ring;
	const rounded = ring.map(([x, y]) => [round(x), round(y)]);
	const closed =
		rounded.length > 1 &&
		rounded[0][0] === rounded.at(-1)[0] &&
		rounded[0][1] === rounded.at(-1)[1];
	const openRing = closed ? rounded.slice(0, -1) : rounded;
	if (openRing.length <= 4 || tolerance <= 0) return rounded;
	const toleranceSquared = tolerance * tolerance;
	const radial = simplifyRadial(openRing, toleranceSquared);
	let simplified = simplifyDouglasPeucker(radial, toleranceSquared);
	if (simplified.length < 3) simplified = openRing;
	if (closed) simplified = [...simplified, simplified[0]];
	return simplified;
}

function simplifyGeometry(geometry, tolerance) {
	if (!geometry) return geometry;
	if (geometry.type === 'Polygon') {
		return {
			type: 'Polygon',
			coordinates: geometry.coordinates.map((ring) => simplifyRing(ring, tolerance))
		};
	}
	if (geometry.type === 'MultiPolygon') {
		return {
			type: 'MultiPolygon',
			coordinates: geometry.coordinates.map((polygon) =>
				polygon.map((ring) => simplifyRing(ring, tolerance))
			)
		};
	}
	return geometry;
}

function polygonArea(rings) {
	const ring = rings?.[0] || [];
	let area = 0;
	for (let index = 0; index < ring.length; index += 1) {
		const current = ring[index];
		const next = ring[(index + 1) % ring.length];
		area += current[0] * next[1] - next[0] * current[1];
	}
	return Math.abs(area / 2);
}

function geometryArea(geometry) {
	if (geometry?.type === 'Polygon') return polygonArea(geometry.coordinates);
	if (geometry?.type === 'MultiPolygon') {
		return geometry.coordinates.reduce((sum, polygon) => sum + polygonArea(polygon), 0);
	}
	return 0;
}

function largestPolygonIndex(geometry) {
	if (geometry?.type !== 'MultiPolygon') return -1;
	let best = 0;
	for (let index = 1; index < geometry.coordinates.length; index += 1) {
		if (polygonArea(geometry.coordinates[index]) > polygonArea(geometry.coordinates[best]))
			best = index;
	}
	return best;
}

function pointCount(geometry) {
	let count = 0;
	const visit = (value) => {
		if (Array.isArray(value) && typeof value[0] === 'number') count += 1;
		else if (Array.isArray(value)) value.forEach(visit);
	};
	visit(geometry?.coordinates);
	return count;
}

async function writeCollection(name, features) {
	const collection = { type: 'FeatureCollection', features };
	const content = JSON.stringify(collection);
	await writeFile(resolve(outputDir, name), content);
	const points = features.reduce((sum, feature) => sum + pointCount(feature.geometry), 0);
	console.log(
		`${name}: ${features.length} features, ${(Buffer.byteLength(content) / 1048576).toFixed(2)} MB, ${points.toLocaleString()} points`
	);
}

await mkdir(outputDir, { recursive: true });
const [countrySource, subdivisionSource, lakeSource] = await Promise.all([
	readJson('countries.geojson'),
	readJson('states-provinces.geojson'),
	readJson('lakes.geojson')
]);

const canonicalByCode = new Map();
for (const feature of countrySource.features) {
	const code = feature.properties.ISO_A2_EH || feature.properties.ISO_A2;
	if (!code || code === '-99') continue;
	const current = canonicalByCode.get(code);
	if (!current || geometryArea(feature.geometry) > geometryArea(current.geometry)) {
		canonicalByCode.set(code, feature);
	}
}

const countries = countrySource.features.map((feature) => {
	const code = feature.properties.ISO_A2_EH || feature.properties.ISO_A2;
	const canonical = canonicalByCode.get(code) === feature;
	return {
		type: 'Feature',
		properties: {
			code: code && code !== '-99' ? code : '',
			labelX: Number.isFinite(feature.properties.LABEL_X)
				? round(feature.properties.LABEL_X)
				: null,
			labelY: Number.isFinite(feature.properties.LABEL_Y)
				? round(feature.properties.LABEL_Y)
				: null,
			canonical,
			mainlandPart: canonical ? largestPolygonIndex(feature.geometry) : -1
		},
		geometry: simplifyGeometry(feature.geometry, countryTolerance)
	};
});

const subdivisions = subdivisionSource.features
	.filter((feature) => ['USA', 'CAN'].includes(feature.properties.adm0_a3))
	.map((feature) => ({
		type: 'Feature',
		properties: {
			id: feature.properties.iso_3166_2,
			countryCode: feature.properties.iso_a2,
			code:
				feature.properties.postal ||
				String(feature.properties.iso_3166_2 || '')
					.split('-')
					.pop(),
			name: feature.properties.name,
			labelX: Number.isFinite(feature.properties.longitude)
				? round(feature.properties.longitude)
				: null,
			labelY: Number.isFinite(feature.properties.latitude)
				? round(feature.properties.latitude)
				: null
		},
		geometry: simplifyGeometry(feature.geometry, subdivisionTolerance)
	}));

const lakes = lakeSource.features
	.filter((feature) => Number(feature.properties.min_zoom) <= 5)
	.map((feature) => ({
		type: 'Feature',
		properties: {},
		geometry: simplifyGeometry(feature.geometry, lakeTolerance)
	}));

await Promise.all([
	writeCollection('countries.compact.geojson', countries),
	writeCollection('us-ca-admin1.compact.geojson', subdivisions),
	writeCollection('lakes.compact.geojson', lakes)
]);
