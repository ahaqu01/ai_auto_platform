const K = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
])
const INITIAL = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]
const rotate = (value: number, bits: number) => (value >>> bits) | (value << (32 - bits))

class Sha256 {
  private readonly state = new Uint32Array(INITIAL)
  private readonly buffer = new Uint8Array(64)
  private buffered = 0
  private bytes = 0

  update(input: Uint8Array): void {
    this.bytes += input.length
    let offset = 0
    while (offset < input.length) {
      const take = Math.min(64 - this.buffered, input.length - offset)
      this.buffer.set(input.subarray(offset, offset + take), this.buffered)
      this.buffered += take
      offset += take
      if (this.buffered === 64) {
        this.process(this.buffer)
        this.buffered = 0
      }
    }
  }

  digestHex(): string {
    const final = new Uint8Array(this.buffered < 56 ? 64 : 128)
    final.set(this.buffer.subarray(0, this.buffered))
    final[this.buffered] = 0x80
    const bitHigh = Math.floor(this.bytes / 0x20000000)
    const bitLow = (this.bytes << 3) >>> 0
    const view = new DataView(final.buffer)
    view.setUint32(final.length - 8, bitHigh)
    view.setUint32(final.length - 4, bitLow)
    for (let offset = 0; offset < final.length; offset += 64) this.process(final.subarray(offset, offset + 64))
    return Array.from(this.state, (word) => word.toString(16).padStart(8, '0')).join('')
  }

  private process(block: Uint8Array): void {
    const words = new Uint32Array(64)
    const view = new DataView(block.buffer, block.byteOffset, block.byteLength)
    for (let index = 0; index < 16; index += 1) words[index] = view.getUint32(index * 4)
    for (let index = 16; index < 64; index += 1) {
      const s0 = rotate(words[index - 15], 7) ^ rotate(words[index - 15], 18) ^ (words[index - 15] >>> 3)
      const s1 = rotate(words[index - 2], 17) ^ rotate(words[index - 2], 19) ^ (words[index - 2] >>> 10)
      words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0
    }
    let [a,b,c,d,e,f,g,h] = this.state
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)
      const choice = (e & f) ^ (~e & g)
      const temp1 = (h + sum1 + choice + K[index] + words[index]) >>> 0
      const sum0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)
      const majority = (a & b) ^ (a & c) ^ (b & c)
      const temp2 = (sum0 + majority) >>> 0
      h=g; g=f; f=e; e=(d+temp1)>>>0; d=c; c=b; b=a; a=(temp1+temp2)>>>0
    }
    const values = [a,b,c,d,e,f,g,h]
    for (let index = 0; index < 8; index += 1) this.state[index] = (this.state[index] + values[index]) >>> 0
  }
}

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error ?? new Error('文件读取失败'))
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.readAsArrayBuffer(blob)
  })
}
export async function sha256File(file: Blob, signal?: AbortSignal, onProgress?: (bytes: number) => void): Promise<string> {
  const digest = new Sha256()
  const chunkSize = 4 * 1024 * 1024
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    if (signal?.aborted) throw new DOMException('摘要计算已取消', 'AbortError')
    const end = Math.min(file.size, offset + chunkSize)
    digest.update(new Uint8Array(await readBlob(file.slice(offset, end))))
    onProgress?.(end)
  }
  return digest.digestHex()
}