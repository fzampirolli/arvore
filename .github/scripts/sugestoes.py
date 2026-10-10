#!/usr/bin/env python3
"""Sugestões da família enviadas como issues do GitHub: leitura e validação.

Este arquivo é independente (só biblioteca padrão) porque também é copiado para o
repositório público do site, onde um robô valida cada sugestão assim que ela chega:

    python3 sugestoes.py validar --evento "$GITHUB_EVENT_PATH" --dados dados.json

O robô NÃO altera dados: ele comenta o que vai mudar, aponta erros prováveis e marca
rótulos. Só quem mantém o site aplica uma sugestão (rótulo "aprovado").
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field

ANO_ATUAL = _dt.date.today().year

# Campos dos formulários (id no YAML -> título no formulário). A ordem é a da tabela.
CAMPOS = {
    "nome_completo": "Nome completo",
    "nascimento_data": "Data de nascimento",
    "nascimento_local": "Local de nascimento",
    "falecimento_data": "Data de falecimento",
    "falecimento_local": "Local de falecimento",
    "outro_genitor": "Outro pai/mãe",
    "unioes": "Cônjuge(s) / uniões",
    "casamento_data": "Data do casamento",
    "casamento_local": "Local do casamento",
    "residencia": "Onde morou",
    "observacao": "Outra correção ou informação",
    "historia": "História ou lembrança",
}
# Campos guardados juntos no DADOS.TXT ("Nascimento: 16/01/2024, Niterói - RJ"),
# mas separados no formulário para poder mudar o local sem perder a data (e vice-versa).
COMPOSTOS = {"nascimento": ("nascimento_data", "nascimento_local"),
             "falecimento": ("falecimento_data", "falecimento_local"),
             "casamento": ("casamento_data", "casamento_local")}
LEGADO = {"Nascimento": "nascimento", "Falecimento": "falecimento", "Casamento": "casamento"}  # formulários antigos

PRIVACIDADE = (
    "#### 🔒 Por que o site mostra só o **ano** de nascimento de quem pode estar vivo?\n"
    "É uma regra de privacidade para pessoas nascidas há menos de 100 anos:\n"
    "1. **Fraude e roubo de identidade:** nome completo, data de nascimento e nomes dos pais são exatamente o que "
    "bancos, operadoras e serviços públicos usam para confirmar quem é a pessoa — e o site é público e aparece no Google.\n"
    "2. **Crianças:** a LGPD (art. 14) exige cuidado especial com dados de crianças; datas completas ligadas aos nomes "
    "dos pais não devem ficar expostas.\n"
    "3. **É o padrão da genealogia:** FamilySearch, MyHeritage e Ancestry escondem dados de pessoas vivas. "
    "As datas completas dos antepassados continuam aparecendo.\n\n"
    "**Esta sugestão também é pública.** Para pessoas vivas, informe aqui só o **ano**. "
    "Se quiser guardar a data completa no arquivo privado da família, fale diretamente com quem mantém o site."
)

_RE_DATA_INICIO = re.compile(
    r"^\s*(~\s*)?(\d{1,2}[-/.]\d{1,2}[-/.](?:\d{4}|\d{2})|(?:\d{1,2}\s+de\s+)?[a-zç]+\s+de\s+\d{4}|\d{4})"
    r"(\s*,?\s*(?:[àa]s\s*)?\d{1,2}(?::\d{2})?\s*h(?:s|oras)?(?:\s*\d{1,2}\s*m(?:in)?)?)?",
    re.IGNORECASE)
_RE_DATA_MEIO = re.compile(r"(~\s*)?\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|1[5-9]\d\d|20\d\d)\b")


def separar_data_local(valor: str) -> tuple[str, str]:
    """'16/01/2024, Niterói - RJ' -> ('16/01/2024', 'Niterói - RJ')."""
    v = " ".join((valor or "").split())
    m = _RE_DATA_INICIO.match(v)
    if m:
        data, resto = m.group(0).strip(" ,"), v[m.end():]
    else:
        m = _RE_DATA_MEIO.search(v)
        if not m:
            return "", v.strip(" ,")
        data, resto = m.group(0).strip(), (v[:m.start()] + " " + v[m.end():])
        resto = re.sub(r"(?i),?\s*[àa]s\s*\d{1,2}(?::\d{2})?\s*h\w*|\b(?:do|no)\s+dia\b", " ", resto)
        resto = re.sub(r"\s+([.,])", r"\1", " ".join(resto.split())).strip(" .,")
    resto = re.sub(r"^[\s,]*(?:(?:em|no|na|local)\b[\s,]*)*", "", resto.strip(), flags=re.IGNORECASE)
    resto = re.sub(r"[\s,]*(?:\b(?:em|no|na)\s*)?$", "", resto, flags=re.IGNORECASE)
    return data, resto.strip(" ,")


def juntar_data_local(data: str, local: str) -> str:
    return ", ".join(x for x in (data.strip(), local.strip()) if x)


def dividir(campos: dict[str, str]) -> dict[str, str]:
    """{'nascimento': '1925, Jaciguá'} -> {'nascimento_data': '1925', 'nascimento_local': 'Jaciguá'}."""
    out = {}
    for k, v in campos.items():
        if k in COMPOSTOS:
            d, l = separar_data_local(v)
            kd, kl = COMPOSTOS[k]
            if d:
                out[kd] = d
            if l:
                out[kl] = l
        else:
            out[k] = v
    return out


FONTES = [
    "Certidão ou documento oficial",
    "Registro de imigração / lista de navio",
    "Registro de igreja (batismo, casamento)",
    "Conheço pessoalmente (sou a pessoa ou parente próximo)",
    "Relato de outro familiar",
    "Outra",
]
APAGAR = "APAGAR"

# Rótulos usados no repositório público
ROTULOS = {
    "sugestão": ("C5E1A5", "Sugestão enviada pelo site"),
    "correção": ("FFE0B2", "Correção de dados de uma pessoa"),
    "nova pessoa": ("B3E5FC", "Pessoa a acrescentar na árvore"),
    "foto ou documento": ("E1BEE7", "Foto ou documento enviado"),
    "validado": ("A5D6A7", "O robô não encontrou problemas"),
    "atenção": ("FFCC80", "O robô encontrou algo a conferir"),
    "dados sensíveis": ("EF9A9A", "Contém telefone, endereço, documento ou data exata de pessoa viva"),
    "conta nova": ("FFF59D", "Conta do GitHub criada há poucos dias"),
    "aprovado": ("2E7D32", "Aprovado: será aplicado automaticamente"),
    "aplicado": ("90A4AE", "Já está no site"),
    "rejeitado": ("BDBDBD", "Não será aplicado"),
    "erro ao aplicar": ("E57373", "A automação não conseguiu aplicar; veja o comentário"),
    "automático": ("80DEEA", "Aprovado automaticamente: pessoa de confiança e nenhum problema encontrado"),
    "forçar": ("6D4C41", "Junto com 'aprovado': aplica mesmo com erros apontados pelo robô"),
}


# ------------------------------------------------------------------ leitura
def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def secoes(corpo: str) -> dict[str, str]:
    """Corpo de issue criado por formulário: '### Título\\n\\nvalor' -> {título: valor}."""
    out: dict[str, str] = {}
    partes = re.split(r"^###\s+(.+?)\s*$", corpo or "", flags=re.M)
    for i in range(1, len(partes), 2):
        valor = partes[i + 1].strip()
        if valor in ("_No response_", "_Sem resposta_", "None"):
            valor = ""
        out[partes[i].strip()] = valor
    return out


@dataclass
class Sugestao:
    numero: int
    tipo: str  # correcao | nova_pessoa | foto
    alvo: str  # caminho da pessoa (correção/foto) ou do pai/mãe (nova pessoa)
    autor_login: str
    campos: dict[str, str] = field(default_factory=dict)
    nome_novo: str = ""
    ordem: str = ""
    fonte: str = ""
    fonte_detalhe: str = ""
    quem_envia: str = ""
    legenda: str = ""
    anexos: list[tuple[str, str]] = field(default_factory=list)  # (nome, url)
    confirmado: bool = False


def caminho_de(texto: str) -> str:
    """'José — 01Giacomo/02Giovanni/01Jose' -> '01Giacomo/02Giovanni/01Jose'."""
    m = re.search(r"([0-9]{2}[^\s/—–-][^\s—–]*(?:/[^\s/—–]+)*)\s*$", texto.strip())
    return m.group(1).strip("/") if m else texto.strip()


def interpretar_issue(issue: dict) -> Sugestao | None:
    rotulos = {(l["name"] if isinstance(l, dict) else l) for l in issue.get("labels", [])}
    s = secoes(issue.get("body") or "")
    titulos = {sem_acento(k): v for k, v in s.items()}

    def campo(titulo: str) -> str:
        return titulos.get(sem_acento(titulo), "").strip()

    if "nova pessoa" in rotulos or campo("Nome da nova pessoa"):
        tipo = "nova_pessoa"
    elif "foto ou documento" in rotulos or campo("Arquivos"):
        tipo = "foto"
    elif "correção" in rotulos or campo("Pessoa"):
        tipo = "correcao"
    else:
        return None

    sug = Sugestao(
        numero=issue.get("number", 0), tipo=tipo,
        alvo=caminho_de(campo("Pai ou mãe") if tipo == "nova_pessoa" else campo("Pessoa")),
        autor_login=(issue.get("user") or {}).get("login", ""),
        nome_novo=campo("Nome da nova pessoa"), ordem=campo("Ordem de nascimento"),
        fonte=campo("Fonte da informação"), fonte_detalhe=campo("Detalhe da fonte"),
        quem_envia=campo("Quem está enviando"), legenda=campo("Legenda"),
        confirmado="[x]" in campo("Confirmações").lower(),
    )
    for chave, titulo in CAMPOS.items():
        v = campo(titulo)
        if v:
            sug.campos[chave] = v
    if campo("Cônjuge") and "unioes" not in sug.campos:  # formulário antigo
        sug.campos["unioes"] = campo("Cônjuge")
    for titulo, base in LEGADO.items():  # issues abertas com o formulário antigo (data e local juntos)
        v = campo(titulo)
        if v:
            for k, val in dividir({base: v}).items():
                sug.campos.setdefault(k, val)
    for texto in (campo("Arquivos"),):
        # Markdown: ![nome](url) ou [arquivo.pdf](url)
        for nome, url in re.findall(r"!?\[([^\]]*)\]\((https://[^)\s\"']+)\)", texto):
            sug.anexos.append((nome or "arquivo", url))
        # HTML (o GitHub insere imagens assim): <img alt="Image" src="https://...">
        for tag in re.findall(r"<img\b[^>]*>", texto, flags=re.I):
            m = re.search(r"""src\s*=\s*["']([^"']+)["']""", tag)
            alt = re.search(r"""alt\s*=\s*["']([^"']*)["']""", tag)
            if m and m.group(1) not in (u for _, u in sug.anexos):
                sug.anexos.append(((alt.group(1) if alt else "") or "imagem", m.group(1)))
        # Endereço solto
        for url in re.findall(r"""(?<![("'=])\b(https://github\.com/user-attachments/[^\s)<>"']+)""", texto):
            if url not in (u for _, u in sug.anexos):
                sug.anexos.append(("arquivo", url))
    return sug


# ---------------------------------------------------------------- validação
_RE_DATA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_RE_ANO = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
SENSIVEIS = [
    (re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}[- ]?\d{4}\b"), "um número de telefone"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "um e-mail"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "um número parecido com CPF"),
    (re.compile(r"(?i)\b(rua|avenida|av\.|travessa|apto|apartamento|cep)\b\s"), "um endereço"),
    (re.compile(r"(?i)\b(rg|cpf|passaporte|codice fiscale)\b"), "um número de documento"),
]


def ano(texto: str) -> int | None:
    m = _RE_DATA.search(texto)
    if m:
        return int(m.group(3))
    m = _RE_ANO.search(texto)
    return int(m.group(1)) if m else None


def checar_data(rotulo: str, texto: str) -> list[tuple[str, str]]:
    probs = []
    for d, m, a in _RE_DATA.findall(texto):
        d, m, a = int(d), int(m), int(a)
        try:
            data = _dt.date(a, m, d)
            if data > _dt.date.today():
                probs.append(("erro", f"{rotulo}: a data {d:02}/{m:02}/{a} está no futuro."))
        except ValueError:
            probs.append(("erro", f"{rotulo}: {d:02}/{m:02}/{a} não é uma data válida (dia/mês/ano)."))
    a = ano(texto)
    if a and a > ANO_ATUAL:
        probs.append(("erro", f"{rotulo}: o ano {a} está no futuro."))
    return probs


def validar(sug: Sugestao, dados: dict, conta_dias: int | None = None) -> tuple[list[tuple[str, str]], set[str]]:
    """Devolve (problemas, rótulos). 'dados' é o dados.json público do site."""
    probs: list[tuple[str, str]] = []
    rotulos: set[str] = set()
    pessoas = dados.get("pessoas", {})
    alvo = pessoas.get(sug.alvo)

    if not alvo:
        probs.append(("erro", f"Não encontrei a pessoa `{sug.alvo}` na árvore. Use o botão na página da pessoa para abrir o formulário."))
    if not sug.confirmado:
        probs.append(("erro", "As confirmações no fim do formulário não foram marcadas."))
    if not sug.fonte:
        probs.append(("aviso", "Não foi informada a fonte da informação."))
    if sug.tipo == "correcao" and not sug.campos:
        probs.append(("erro", "Nenhum campo foi alterado."))
    if sug.tipo == "nova_pessoa" and not sug.nome_novo:
        probs.append(("erro", "Falta o nome da nova pessoa."))
    if sug.tipo == "foto" and not sug.anexos:
        probs.append(("erro", "Nenhum arquivo foi anexado (arraste a foto ou o PDF para o campo “Arquivos”)."))

    for chave in ("nascimento_data", "falecimento_data", "casamento_data"):
        if chave in sug.campos:
            probs += checar_data(CAMPOS[chave], sug.campos[chave])

    # Coerência entre gerações
    if alvo:
        pessoa = alvo if sug.tipo != "nova_pessoa" else {"ano": None, "pai": sug.alvo, "filhos": alvo.get("filhos", [])[:0]}
        nasc = ano(sug.campos.get("nascimento_data", "")) or pessoa.get("ano")
        pai = pessoas.get(pessoa.get("pai") or "")
        if nasc and pai and pai.get("ano"):
            dif = nasc - pai["ano"]
            if dif < 13:
                probs.append(("erro", f"Nascimento em {nasc}, mas {pai['n']} (pai/mãe) nasceu em {pai['ano']}: diferença de {dif} anos."))
            elif dif > 65:
                probs.append(("aviso", f"Diferença de {dif} anos para {pai['n']} (pai/mãe). Confira."))
        if nasc and sug.tipo == "correcao":
            for f in pessoa.get("filhos", []):
                fa = pessoas.get(f, {}).get("ano")
                if fa and fa - nasc < 13:
                    probs.append(("erro", f"Nascimento em {nasc}, mas o(a) filho(a) {pessoas[f]['n']} nasceu em {fa}."))
        fal = ano(sug.campos.get("falecimento_data", ""))
        if fal and nasc:
            if fal < nasc:
                probs.append(("erro", f"Falecimento ({fal}) antes do nascimento ({nasc})."))
            elif fal - nasc > 115:
                probs.append(("aviso", f"Idade de {fal - nasc} anos ao falecer. Confira."))
        cas = ano(sug.campos.get("casamento_data", ""))
        if cas and nasc and cas - nasc < 14:
            probs.append(("erro", f"Casamento em {cas} com a pessoa nascida em {nasc}."))
        if sug.tipo == "nova_pessoa":
            irmaos = [pessoas.get(c, {}).get("n", "") for c in alvo.get("filhos", [])]
            primeiro = sem_acento(sug.nome_novo.split()[0]) if sug.nome_novo.split() else ""
            for n in irmaos:
                if primeiro and sem_acento(n.split()[0] if n.split() else "") == primeiro:
                    probs.append(("aviso", f"Já existe {n} entre os filhos de {alvo['n']}. Não é a mesma pessoa?"))

    # Privacidade: issues são públicas
    vivo = bool(alvo and alvo.get("vivo")) if sug.tipo != "nova_pessoa" else not (sug.campos.get("falecimento_data") or sug.campos.get("falecimento_local"))
    texto = " ".join([*sug.campos.values(), sug.fonte_detalhe, sug.legenda, sug.nome_novo])
    for regex, nome in SENSIVEIS:
        if regex.search(texto):
            probs.append(("sensivel", f"A sugestão parece conter {nome}. Esta página é pública: edite a issue e remova."))
    if vivo and _RE_DATA.search(" ".join(sug.campos.get(k, "") for k in ("nascimento_data", "casamento_data", "unioes"))):
        probs.append(("sensivel", "Data completa de uma pessoa que pode estar viva. O site público mostra só o ano; prefira informar só o ano."))

    # Vandalismo / spam
    links = re.findall(r"https?://", texto)
    if len(links) > 2:
        probs.append(("aviso", "Muitos links externos."))
    if conta_dias is not None and conta_dias < 14:
        rotulos.add("conta nova")
        probs.append(("aviso", f"Conta do GitHub criada há {conta_dias} dia(s)."))
    for v in sug.campos.values():
        if v.strip().upper() == APAGAR:
            probs.append(("aviso", "A sugestão pede para APAGAR uma informação. Confira o motivo."))
            break

    if any(n == "sensivel" for n, _ in probs):
        rotulos.add("dados sensíveis")
    rotulos.add("atenção" if any(n in ("erro", "aviso", "sensivel") for n, _ in probs) else "validado")
    return probs, rotulos


def so_alterados(sug: Sugestao, dados: dict) -> Sugestao:
    """Os formulários vêm preenchidos com os valores atuais: descarta o que não mudou."""
    atuais = dados.get("pessoas", {}).get(sug.alvo, {}).get("campos", {}) if sug.tipo == "correcao" else {}
    norm = lambda v: " ".join(sem_acento(v).split())
    sug.campos = {k: v for k, v in sug.campos.items() if norm(v) != norm(atuais.get(k, ""))}
    return sug


def aprovar_automaticamente(sug: Sugestao, rotulos: set[str], dados: dict) -> tuple[bool, str]:
    """Meio-termo entre revisar tudo e aprovar tudo. Só passa sozinho se TODAS as condições valerem."""
    regra = dados.get("aprovacao_automatica") or {}
    confiaveis = {u.lower() for u in regra.get("confiaveis", [])}
    tipos = set(regra.get("tipos", ["correcao", "nova_pessoa"]))
    if not confiaveis:
        return False, "aprovação automática desligada"
    if sug.autor_login.lower() not in confiaveis:
        return False, "quem enviou não está na lista de confiança"
    if sug.tipo not in tipos:
        return False, "fotos e documentos sempre esperam revisão"
    if rotulos != {"validado"}:
        return False, "o robô encontrou pontos a conferir"
    if any(v.strip().upper() == APAGAR for v in sug.campos.values()):
        return False, "pedidos para APAGAR sempre esperam revisão"
    return True, "pessoa de confiança, sem problemas encontrados"


def comentario(sug: Sugestao, dados: dict, probs, rotulos) -> str:
    pessoas = dados.get("pessoas", {})
    alvo = pessoas.get(sug.alvo, {})
    site = dados.get("site", "").rstrip("/")
    L = ["<!-- robo-arvore -->", "### 🌳 Conferência automática", ""]
    nome = alvo.get("n", sug.alvo)
    link = f"[{nome}]({site}/{alvo.get('u', '')})" if site and alvo else nome
    if sug.tipo == "correcao":
        L += [f"**Correção em:** {link}", "", "| Campo | Hoje no site | Sugestão |", "|---|---|---|"]
        atuais = alvo.get("campos", {})
        for k, v in sug.campos.items():
            atual = atuais.get(k, "") or "—"
            L.append(f"| {CAMPOS[k]} | {atual.replace('|', '/')} | **{v.replace('|', '/').replace(chr(10), ' ')}** |")
    elif sug.tipo == "nova_pessoa":
        L += [f"**Nova pessoa:** {sug.nome_novo} — filho(a) de {link}", ""]
        L += [f"- {CAMPOS[k]}: {v}" for k, v in sug.campos.items()]
    else:
        L += [f"**Arquivos para:** {link}", f"**Legenda:** {sug.legenda or '—'}", ""]
        L += [f"- {n}" for n, _ in sug.anexos]
    L += ["", f"**Fonte:** {sug.fonte or '—'}{' — ' + sug.fonte_detalhe if sug.fonte_detalhe else ''}", ""]
    icones = {"erro": "❌", "aviso": "⚠️", "sensivel": "🔒"}
    if probs:
        L += ["**Pontos a conferir:**", ""] + [f"- {icones[n]} {m}" for n, m in probs]
    else:
        L.append("✅ Nenhum problema encontrado.")
    L += ["", "---",
          "_Quem mantém o site revisa todas as sugestões. Se algo estiver errado, **edite a issue** (menu ··· › Edit) "
          "que esta conferência é refeita. Para aprovar, o mantenedor adiciona o rótulo `aprovado`._"]
    return "\n".join(L)


# ------------------------------------------------------------- API GitHub
def api(metodo: str, url: str, dados=None, token: str | None = None):
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(
        url if url.startswith("http") else "https://api.github.com" + url, method=metodo,
        data=json.dumps(dados).encode() if dados is not None else None,
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corpo = r.read()
            return json.loads(corpo) if corpo else None
    except urllib.error.HTTPError as e:
        if e.code == 422 and "/labels" in url and metodo == "POST":
            return None  # rótulo já existe
        raise


def garantir_rotulos(repo: str, token: str | None = None):
    for nome, (cor, desc) in ROTULOS.items():
        try:
            api("POST", f"/repos/{repo}/labels", {"name": nome, "color": cor, "description": desc}, token)
        except urllib.error.HTTPError:
            pass


def comentar_unico(repo: str, numero: int, texto: str, token: str | None = None):
    """Atualiza o comentário do robô, se já existir, em vez de criar outro."""
    for c in api("GET", f"/repos/{repo}/issues/{numero}/comments?per_page=100", token=token) or []:
        if "<!-- robo-arvore -->" in (c.get("body") or ""):
            api("PATCH", f"/repos/{repo}/issues/comments/{c['id']}", {"body": texto}, token)
            return
    api("POST", f"/repos/{repo}/issues/{numero}/comments", {"body": texto}, token)


def cmd_validar(args):
    evento = json.load(open(args.evento, encoding="utf-8"))
    issue = evento["issue"]
    repo = evento["repository"]["full_name"]
    sug = interpretar_issue(issue)
    if not sug:
        print("Issue não é uma sugestão de formulário; nada a fazer.")
        return 0
    dados = json.load(open(args.dados, encoding="utf-8"))
    so_alterados(sug, dados)
    dias = None
    try:
        criado = api("GET", f"/users/{sug.autor_login}")["created_at"][:10]
        dias = (_dt.date.today() - _dt.date.fromisoformat(criado)).days
    except Exception:
        pass
    probs, rotulos = validar(sug, dados, dias)
    texto = comentario(sug, dados, probs, rotulos)
    if args.simular:
        print(texto, "\nRótulos:", rotulos)
        return 0
    auto, motivo = aprovar_automaticamente(sug, rotulos, dados)
    ja_tratada = issue.get("state") == "closed" or {(l["name"] if isinstance(l, dict) else l) for l in issue.get("labels", [])} & {"aprovado", "aplicado", "rejeitado"}
    if auto and not ja_tratada:
        texto += ("\n\n🤖 **Aprovada automaticamente** (" + motivo + "). Será aplicada em instantes; "
                  "o mantenedor pode desfazer pelo histórico do repositório de dados.")
        rotulos |= {"aprovado", "automático"}
    garantir_rotulos(repo)
    comentar_unico(repo, issue["number"], texto)
    # troca validado/atenção conforme o resultado atual
    for velho in ({"validado", "atenção"} - rotulos):
        try:
            api("DELETE", f"/repos/{repo}/issues/{issue['number']}/labels/{urllib.request.quote(velho)}")
        except urllib.error.HTTPError:
            pass
    api("POST", f"/repos/{repo}/issues/{issue['number']}/labels", {"labels": sorted(rotulos)})
    if auto and not ja_tratada:
        # Rótulos colocados por robôs não disparam outras automações no GitHub:
        # por isso o aviso ao repositório de dados é feito aqui, diretamente.
        repo_dados, token = os.environ.get("REPO_DADOS"), os.environ.get("TOKEN_ARVORE")
        if repo_dados and token:
            api("POST", f"/repos/{repo_dados}/dispatches",
                {"event_type": "sugestao-aprovada", "client_payload": {"issue": issue["number"], "automatica": True}}, token)
        else:
            print("Aviso: falta REPO_DADOS ou TOKEN_ARVORE; a aprovação automática não foi enviada.")
    print(texto)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validar", help="confere uma issue recém-aberta ou editada")
    v.add_argument("--evento", required=True)
    v.add_argument("--dados", default="dados.json")
    v.add_argument("--simular", action="store_true", help="só mostra o comentário, sem chamar a API")
    args = ap.parse_args(argv)
    return cmd_validar(args)


if __name__ == "__main__":
    sys.exit(main())
