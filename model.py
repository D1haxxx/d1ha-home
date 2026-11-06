"""Small character GPT based on Andrej Karpathy's microGPT, using PyTorch.
https://karpathy.github.io/2026/02/12/microgpt/
Randomly initialized: no pretrained model or paid API.
"""
import torch
from torch import nn
from torch.nn import functional as F


def rmsnorm(x):
    return x * torch.rsqrt(x.square().mean(-1, keepdim=True) + 1e-5)


class Block(nn.Module):
    def __init__(self, width, heads):
        super().__init__()
        self.heads = heads
        self.qkv = nn.Linear(width, width * 3, bias=False)
        self.projection = nn.Linear(width, width, bias=False)
        self.mlp = nn.Sequential(nn.Linear(width, width * 4, bias=False),
                                 nn.ReLU(), nn.Linear(width * 4, width, bias=False))

    def forward(self, x):
        batch, length, width = x.shape
        q, k, v = self.qkv(rmsnorm(x)).chunk(3, dim=-1)
        q, k, v = [t.view(batch, length, self.heads, width // self.heads)
                   .transpose(1, 2) for t in (q, k, v)]
        # Each position sees only itself and the preceding characters.
        attention = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        attention = attention.transpose(1, 2).contiguous().view(batch, length, width)
        x = x + self.projection(attention)
        return x + self.mlp(rmsnorm(x))


class MicroGPT(nn.Module):
    def __init__(self, vocab_size, width=32, heads=4, layers=1, context=128):
        super().__init__()
        if width % heads:
            raise ValueError('Width must be divisible by heads')
        self.context = context
        self.characters = nn.Embedding(vocab_size, width)
        self.positions = nn.Embedding(context, width)
        self.blocks = nn.Sequential(*[Block(width, heads) for _ in range(layers)])
        self.output = nn.Linear(width, vocab_size, bias=False)
        for parameter in self.parameters():
            nn.init.normal_(parameter, std=0.08)

    def forward(self, tokens):
        positions = torch.arange(tokens.shape[1], device=tokens.device)
        x = rmsnorm(self.characters(tokens) + self.positions(positions))
        return self.output(self.blocks(x))

    @torch.inference_mode()
    def reply(self, message, chars, temperature=0.5, max_new=100, usage=None, top_k=None):
        if usage is not None:
            usage.update(prompt_tokens=0, generated_tokens=0)
        prompt = f'User: {message}\nBot:'
        missing = sorted(set(prompt) - set(chars))
        if missing:
            return f'I have not learned these characters yet: {missing!r}'
        if len(prompt) >= self.context:
            return 'Please try a shorter message.'
        lookup = {c: i for i, c in enumerate(chars)}
        device = next(self.parameters()).device
        tokens = torch.tensor([[lookup[c] for c in prompt]], device=device)
        if usage is not None:
            usage['prompt_tokens'] = len(prompt)
        reply = []
        for _ in range(min(max_new, self.context - len(prompt))):
            logits = self(tokens)[:, -1, :]
            if top_k is not None:
                cutoff = logits.topk(min(top_k, logits.shape[-1]), dim=-1).values[:, -1:]
                logits = logits.masked_fill(logits < cutoff, float('-inf'))
            if temperature == 0:
                number = logits.argmax(dim=-1).item()
            else:
                number = torch.multinomial(torch.softmax(logits / temperature, -1), 1).item()
            if usage is not None:
                usage['generated_tokens'] += 1
            if number == len(chars):  # End of this conversation example.
                break
            reply.append(chars[number])
            tokens = torch.cat((tokens, torch.tensor([[number]], device=device)), dim=1)
        return ''.join(reply).strip() or '(No reply generated. Try again.)'
