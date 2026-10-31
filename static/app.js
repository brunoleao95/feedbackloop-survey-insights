// Interface do FeedbackLoop. Sem framework e sem dependência externa: a página
// fala com a API de app.py e desenha o resultado.

const $ = (id) => document.getElementById(id);
const CORES = { positivo: "var(--positivo)", neutro: "var(--neutro)", negativo: "var(--negativo)" };
const ROTULOS = { positivo: "Positivo", neutro: "Neutro", negativo: "Negativo" };

const estado = { aba: "exemplo", respostas: { exemplo: [], colar: [], csv: [] }, resultado: null };

function escapar(texto) {
  return String(texto).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function mostrarErro(mensagem) {
  $("erro").textContent = mensagem;
  $("erro").hidden = !mensagem;
}

function atualizarContagem() {
  const n = estado.respostas[estado.aba].length;
  $("contagem").textContent = n ? `${n} resposta${n > 1 ? "s" : ""} pronta${n > 1 ? "s" : ""} para análise` : "";
  $("analisar").disabled = n === 0;
}

// ---------------------------------------------------------------- entrada

document.querySelectorAll(".aba").forEach((aba) => {
  aba.addEventListener("click", () => {
    estado.aba = aba.dataset.aba;
    document.querySelectorAll(".aba").forEach((a) => {
      a.classList.toggle("ativa", a === aba);
      a.setAttribute("aria-selected", a === aba);
    });
    document.querySelectorAll(".painel").forEach((p) => (p.hidden = p.dataset.painel !== estado.aba));
    mostrarErro("");
    atualizarContagem();
  });
});

$("texto").addEventListener("input", (e) => {
  estado.respostas.colar = e.target.value.split("\n").map((l) => l.trim()).filter(Boolean);
  atualizarContagem();
});

async function lerCsv(arquivo) {
  mostrarErro("");
  if (!arquivo) return;
  const resposta = await fetch("/api/csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conteudo: await arquivo.text() }),
  });
  const corpo = await resposta.json();
  if (!resposta.ok) {
    estado.respostas.csv = [];
    mostrarErro(corpo.detail || "Não consegui ler o arquivo.");
  } else {
    estado.respostas.csv = corpo.respostas;
  }
  atualizarContagem();
}

$("arquivo").addEventListener("change", (e) => lerCsv(e.target.files[0]));
const soltar = $("soltar");
soltar.addEventListener("dragover", (e) => { e.preventDefault(); soltar.classList.add("sobre"); });
soltar.addEventListener("dragleave", () => soltar.classList.remove("sobre"));
soltar.addEventListener("drop", (e) => {
  e.preventDefault();
  soltar.classList.remove("sobre");
  lerCsv(e.dataTransfer.files[0]);
});

fetch("/api/exemplo")
  .then((r) => r.json())
  .then((corpo) => { estado.respostas.exemplo = corpo.respostas; atualizarContagem(); })
  .catch(() => mostrarErro("Não consegui carregar os dados de exemplo."));

// ---------------------------------------------------------------- análise

function progresso(feitas, total) {
  const pct = Math.round((feitas / total) * 100);
  $("barra").style.width = `${pct}%`;
  $("andamento-pct").textContent = `${pct}%`;
  document.querySelector(".barra").setAttribute("aria-valuenow", pct);
  $("andamento-texto").textContent = feitas < total - 1
    ? `Classificando resposta ${feitas + 1} de ${total - 1}`
    : feitas < total ? "Escrevendo o resumo para a liderança" : "Pronto";
}

$("analisar").addEventListener("click", async () => {
  const respostas = estado.respostas[estado.aba];
  mostrarErro("");
  $("analisar").disabled = true;
  $("resultado").hidden = true;
  $("andamento").hidden = false;
  progresso(0, respostas.length + 1);
  $("andamento-texto").textContent = "Mascarando dados pessoais";

  try {
    const resposta = await fetch("/api/analisar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ respostas }),
    });
    if (!resposta.ok) {
      const corpo = await resposta.json().catch(() => ({}));
      throw new Error(corpo.detail || `O servidor respondeu ${resposta.status}.`);
    }
    // NDJSON: uma linha por evento, lida conforme chega.
    const leitor = resposta.body.getReader();
    const decodificador = new TextDecoder();
    let pendente = "";
    for (;;) {
      const { value, done } = await leitor.read();
      if (done) break;
      pendente += decodificador.decode(value, { stream: true });
      const linhas = pendente.split("\n");
      pendente = linhas.pop();
      for (const linha of linhas.filter(Boolean)) {
        const evento = JSON.parse(linha);
        if (evento.tipo === "progresso") progresso(evento.feitas, evento.total);
        else if (evento.tipo === "erro") throw new Error(evento.mensagem);
        else if (evento.tipo === "resultado") desenhar(evento);
      }
    }
  } catch (erro) {
    mostrarErro(`${erro.message} Tente de novo em instantes.`);
  } finally {
    $("andamento").hidden = true;
    $("analisar").disabled = false;
  }
});

// ---------------------------------------------------------------- resultado

// Markdown mínimo para o texto do modelo: parágrafos, listas, títulos e negrito.
// O texto é escapado antes, então nada do que o modelo devolve vira HTML.
function markdown(texto) {
  const negrito = (s) => escapar(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  let html = "";
  let lista = null;
  const fechar = () => { if (lista) { html += `</${lista}>`; lista = null; } };
  for (const bruta of texto.split("\n")) {
    const linha = bruta.trim();
    const item = linha.match(/^([-*•]|\d+[.)])\s+(.*)$/);
    if (item) {
      const tipo = /\d/.test(item[1]) ? "ol" : "ul";
      if (lista !== tipo) { fechar(); html += `<${tipo}>`; lista = tipo; }
      html += `<li>${negrito(item[2])}</li>`;
    } else if (!linha) {
      fechar();
    } else if (/^#{1,6}\s/.test(linha)) {
      fechar();
      html += `<h3>${negrito(linha.replace(/^#+\s*/, ""))}</h3>`;
    } else {
      fechar();
      html += `<p>${negrito(linha)}</p>`;
    }
  }
  fechar();
  return html;
}

function realcarMarcadores(texto) {
  return escapar(texto).replace(/\[(PESSOA|EMAIL|CPF|TELEFONE)\]/g, "<mark>[$1]</mark>");
}

function desenhar(r) {
  estado.resultado = r;
  const total = r.total || 1;
  const pct = (n) => `${Math.round((n / total) * 100)}%`;

  $("i-total").textContent = r.total;
  $("i-negativo").textContent = pct(r.sentimentos.negativo || 0);
  $("i-tema").textContent = r.temas[0] ? r.temas[0].tema : "–";
  $("i-tema").title = $("i-tema").textContent;
  const etapas = r.chamadas_llm + r.acertos_cache;
  $("i-tempo").textContent = r.duracao_s < 1 ? "< 1 s" : `${Math.round(r.duracao_s)} s`;
  $("i-tempo-legenda").textContent = r.acertos_cache
    ? `${r.acertos_cache} de ${etapas} etapas vieram do cache, sem custo`
    : "tempo de análise";

  $("resumo").innerHTML = markdown(r.texto_resumo || "O modelo não devolveu texto.");

  $("sentimentos").innerHTML = ["positivo", "neutro", "negativo"]
    .map((s) => `<span style="width:${pct(r.sentimentos[s] || 0)};background:${CORES[s]}" title="${ROTULOS[s]}"></span>`)
    .join("");
  $("sentimentos-legenda").innerHTML = ["positivo", "neutro", "negativo"]
    .map((s) => `<li><i style="background:${CORES[s]}"></i>${ROTULOS[s]} ${r.sentimentos[s] || 0} (${pct(r.sentimentos[s] || 0)})</li>`)
    .join("");

  // Cada tema mostra a divisão de sentimento dentro dele: "Liderança: 4" diz
  // pouco; "Liderança: 4, todas negativas" é o que orienta a ação.
  const maior = Math.max(...r.temas.map((t) => t.quantidade), 1);
  $("temas").innerHTML = r.temas.map((t) => {
    const doTema = r.classificacoes.filter((c) => c.tema === t.tema);
    const partes = ["negativo", "neutro", "positivo"].map((s) => {
      const n = doTema.filter((c) => c.sentimento === s).length;
      return n ? `<span style="width:${(n / maior) * 100}%;background:${CORES[s]}" title="${ROTULOS[s]}: ${n}"></span>` : "";
    }).join("");
    const negativos = doTema.filter((c) => c.sentimento === "negativo").length;
    return `<li><div class="tema-linha"><span>${escapar(t.tema)}</span><span>${t.quantidade} · ${negativos} negativa${negativos === 1 ? "" : "s"}</span></div><div class="tema-barra">${partes}</div></li>`;
  }).join("");

  const mascarados = Object.values(r.pii_mascarada).reduce((a, b) => a + b, 0);
  const NOMES = { pessoa: ["nome", "nomes"], email: ["e-mail", "e-mails"], cpf: ["CPF", "CPFs"], telefone: ["telefone", "telefones"] };
  const tipos = Object.entries(r.pii_mascarada)
    .map(([tipo, n]) => `${n} ${(NOMES[tipo] || [tipo, tipo])[n === 1 ? 0 : 1]}`)
    .join(", ");
  const alteradas = r.classificacoes.filter((c) => c.texto_enviado !== c.resposta);
  $("pii-texto").innerHTML = mascarados
    ? `<strong>${mascarados} dado${mascarados > 1 ? "s" : ""} pessoal${mascarados > 1 ? "is" : ""} mascarado${mascarados > 1 ? "s" : ""}</strong> antes do envio ao provedor de IA (${escapar(tipos)}). O texto original não sai do servidor.`
    : "Nenhum dado pessoal foi detectado nas respostas.";
  $("pii-detalhes").hidden = alteradas.length === 0;
  $("pii-lista").innerHTML = alteradas.map((c) =>
    `<div class="par"><div><b>Original</b>${escapar(c.resposta)}</div><div><b>Enviado</b>${realcarMarcadores(c.texto_enviado)}</div></div>`
  ).join("");

  const temas = [...new Set(r.classificacoes.map((c) => c.tema))].sort();
  $("filtro-tema").innerHTML = `<option value="">Todos os temas</option>` +
    temas.map((t) => `<option value="${escapar(t)}">${escapar(t)}</option>`).join("");
  $("filtro-sentimento").value = "";
  desenharLinhas();

  $("resultado").hidden = false;
  $("resultado").scrollIntoView({ behavior: "smooth", block: "start" });
}

function desenharLinhas() {
  const tema = $("filtro-tema").value;
  const sentimento = $("filtro-sentimento").value;
  $("linhas").innerHTML = estado.resultado.classificacoes
    .filter((c) => (!tema || c.tema === tema) && (!sentimento || c.sentimento === sentimento))
    .map((c) => `<tr><td>${escapar(c.resposta)}</td><td>${escapar(c.tema)}</td><td><span class="etiqueta ${c.sentimento}">${ROTULOS[c.sentimento]}</span></td></tr>`)
    .join("");
}

$("filtro-tema").addEventListener("change", desenharLinhas);
$("filtro-sentimento").addEventListener("change", desenharLinhas);

$("copiar").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(estado.resultado.texto_resumo);
    $("copiar").textContent = "Copiado";
  } catch {
    $("copiar").textContent = "Não foi possível copiar";
  }
  setTimeout(() => ($("copiar").textContent = "Copiar resumo"), 2000);
});

$("baixar").addEventListener("click", () => {
  const celula = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const linhas = [["resposta", "tema", "sentimento"].join(",")].concat(
    estado.resultado.classificacoes.map((c) => [c.resposta, c.tema, c.sentimento].map(celula).join(","))
  );
  // BOM no início para o Excel abrir os acentos corretamente.
  const blob = new Blob(["﻿" + linhas.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(blob),
    download: "feedbackloop-resultado.csv",
  });
  link.click();
  URL.revokeObjectURL(link.href);
});
