// Which chunks slimes spawn in, the way Bedrock decides it: not from the world seed, as Java does, but
// from the chunk's own position. The chunk's x times 0x1f1f1f1f, kept to 32 bits, xor its z, seeds a
// Mersenne Twister (MT19937), and the chunk is a slime chunk when the first number it gives is a
// multiple of ten. Found by the slime-finder-pe project; SlimeChunkFinderAddonBE does the same.

const known = new Map();   // "x,z" of a chunk -> whether slimes spawn in it
const MAX_KNOWN = 4096;

/** Whether the chunk at chunk coordinates x, z is a slime chunk. */
export function isSlimeChunk(x, z) {
	const key = `${x},${z}`;
	let slime = known.get(key);
	if (slime !== undefined) return slime;
	slime = firstNumber((Math.imul(x, 0x1f1f1f1f) ^ z) >>> 0) % 10 === 0;
	if (known.size >= MAX_KNOWN) known.clear();
	known.set(key, slime);
	return slime;
}

/** The first number MT19937 gives for a seed. Only entries 0, 1 and 397 of its state go into it, so
the state is only filled that far. */
function firstNumber(seed) {
	const state = new Uint32Array(398);
	state[0] = seed;
	for (let i = 1; i < 398; i++) {
		const previous = state[i - 1] ^ (state[i - 1] >>> 30);
		state[i] = Math.imul(1812433253, previous) + i;
	}
	const y = (state[0] & 0x80000000) | (state[1] & 0x7fffffff);
	let value = state[397] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
	value ^= value >>> 11;
	value ^= (value << 7) & 0x9d2c5680;
	value ^= (value << 15) & 0xefc60000;
	value ^= value >>> 18;
	return value >>> 0;
}
