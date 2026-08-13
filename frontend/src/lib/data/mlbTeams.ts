export type MlbTeamMeta = {
	id: string;
	abbr: string;
	primary: string;
	secondary: string;
	offset: [number, number];
};

const logoBase = 'https://a.espncdn.com/i/teamlogos/mlb/500';

export const mlbTeamMeta: Record<string, MlbTeamMeta> = {
	'Arizona Diamondbacks': { id: 'ARI', abbr: 'ARI', primary: '#A71930', secondary: '#E3D4AD', offset: [22, 8] },
	'Atlanta Braves': { id: 'ATL', abbr: 'ATL', primary: '#CE1141', secondary: '#13274F', offset: [22, 14] },
	'Baltimore Orioles': { id: 'BAL', abbr: 'BAL', primary: '#DF4601', secondary: '#000000', offset: [42, 38] },
	'Boston Red Sox': { id: 'BOS', abbr: 'BOS', primary: '#BD3039', secondary: '#0C2340', offset: [55, -24] },
	'Chicago Cubs': { id: 'CHC', abbr: 'CHC', primary: '#0E3386', secondary: '#CC3433', offset: [-35, -30] },
	'Chicago White Sox': { id: 'CHW', abbr: 'CWS', primary: '#27251F', secondary: '#C4CED4', offset: [32, 24] },
	'Cincinnati Reds': { id: 'CIN', abbr: 'CIN', primary: '#C6011F', secondary: '#FFFFFF', offset: [-28, 24] },
	'Cleveland Guardians': { id: 'CLE', abbr: 'CLE', primary: '#00385D', secondary: '#E50022', offset: [22, -20] },
	'Colorado Rockies': { id: 'COL', abbr: 'COL', primary: '#333366', secondary: '#C4CED4', offset: [0, -36] },
	'Detroit Tigers': { id: 'DET', abbr: 'DET', primary: '#0C2340', secondary: '#FA4616', offset: [-4, -38] },
	'Houston Astros': { id: 'HOU', abbr: 'HOU', primary: '#002D62', secondary: '#EB6E1F', offset: [24, 34] },
	'Kansas City Royals': { id: 'KC', abbr: 'KC', primary: '#004687', secondary: '#BD9B60', offset: [-30, -20] },
	'Los Angeles Angels': { id: 'LAA', abbr: 'LAA', primary: '#BA0021', secondary: '#003263', offset: [30, 24] },
	'Los Angeles Dodgers': { id: 'LAD', abbr: 'LAD', primary: '#005A9C', secondary: '#EF3E42', offset: [-34, -14] },
	'Miami Marlins': { id: 'MIA', abbr: 'MIA', primary: '#00A3E0', secondary: '#EF3340', offset: [42, 18] },
	'Milwaukee Brewers': { id: 'MIL', abbr: 'MIL', primary: '#12284B', secondary: '#FFC52F', offset: [10, -42] },
	'Minnesota Twins': { id: 'MIN', abbr: 'MIN', primary: '#002B5C', secondary: '#D31145', offset: [-18, -38] },
	'New York Mets': { id: 'NYM', abbr: 'NYM', primary: '#002D72', secondary: '#FF5910', offset: [62, 26] },
	'New York Yankees': { id: 'NYY', abbr: 'NYY', primary: '#0C2340', secondary: '#C4CED4', offset: [58, -12] },
	'Oakland Athletics': { id: 'ATH', abbr: 'ATH', primary: '#003831', secondary: '#EFB21E', offset: [-34, 32] },
	'Philadelphia Phillies': { id: 'PHI', abbr: 'PHI', primary: '#E81828', secondary: '#002D72', offset: [36, 28] },
	'Pittsburgh Pirates': { id: 'PIT', abbr: 'PIT', primary: '#27251F', secondary: '#FDB827', offset: [28, -28] },
	'San Diego Padres': { id: 'SD', abbr: 'SD', primary: '#2F241D', secondary: '#FFC425', offset: [-22, 38] },
	'San Francisco Giants': { id: 'SF', abbr: 'SF', primary: '#FD5A1E', secondary: '#27251F', offset: [-42, -18] },
	'Seattle Mariners': { id: 'SEA', abbr: 'SEA', primary: '#0C2C56', secondary: '#005C5C', offset: [18, 20] },
	'St. Louis Cardinals': { id: 'STL', abbr: 'STL', primary: '#C41E3A', secondary: '#0C2340', offset: [-30, 26] },
	'Tampa Bay Rays': { id: 'TB', abbr: 'TB', primary: '#092C5C', secondary: '#8FBCE6', offset: [18, 34] },
	'Texas Rangers': { id: 'TEX', abbr: 'TEX', primary: '#003278', secondary: '#C0111F', offset: [20, 20] },
	'Toronto Blue Jays': { id: 'TOR', abbr: 'TOR', primary: '#134A8E', secondary: '#E8291C', offset: [6, -42] },
	'Washington Nationals': { id: 'WSH', abbr: 'WSH', primary: '#AB0003', secondary: '#14225A', offset: [14, 58] }
};

export function mlbLogoUrl(team: MlbTeamMeta): string {
	return `${logoBase}/${team.id.toLowerCase()}.png`;
}
