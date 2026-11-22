"""Generate bounded frame JSON for `magical-led play`; no Bluetooth I/O.

Run: python examples/moving_dot.py --output moving-dot.json
Output is UTF-8, created exclusively so existing files are not overwritten.
"""
import argparse
import json


def dimension(text):
    value = int(text)
    if not 1 <= value <= 256:
        raise argparse.ArgumentTypeError('expected an integer 1..256')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=dimension, default=20)
    parser.add_argument('--height', type=dimension, default=26)
    parser.add_argument('--frames', type=dimension, default=4)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.width * args.height * args.frames > 100000:
        parser.error('example limited to 100000 pixel values total')
    colors = (0xff0000, 0x00ff00, 0x0000ff, 0xffff00)
    frames = []
    for i in range(args.frames):
        frame = [[0 for _ in range(args.width)] for _ in range(args.height)]
        frame[0][i % args.width] = colors[i % len(colors)]
        frames.append(frame)
    with open(args.output, 'x', encoding='utf-8') as output:
        json.dump({'frames': frames}, output)


if __name__ == '__main__':
    main()
