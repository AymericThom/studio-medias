"""Met le studio en ligne sur GitHub, gratuit, 24h/24, même PC éteint. Tout est automatique.

Le plus simple : double-clique sur METTRE_EN_LIGNE.bat (il installe Git et GitHub CLI si besoin, puis lance ce fichier).
À relancer après chaque mise à jour du studio ou de tes réglages : il renvoie le code et les clés.

Ce que fait ce programme :
  1. te connecte à ton compte GitHub (une page s'ouvre dans ton navigateur, tu cliques sur « Authorize ») ;
  2. crée ton dépôt (public, obligatoire pour les minutes gratuites illimitées) et y envoie le code, SANS data/ ni clés ;
  3. copie tes clés depuis le studio (Gemini, Buffer, ntfy…) dans les « secrets » chiffrés du dépôt ;
  4. active la page des posts (GitHub Pages) et le robot (GitHub Actions), puis lance un premier passage.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
DEPOT = SRC.parent / "depot_github"               # copie du code suivie par Git (jamais data/ ni clés)
MEMO = SRC / "data" / "github.json"               # nom du dépôt choisi (reste sur ton PC)
EXCLUS = {"data", "site", "__pycache__", ".venv", ".git", ".claude"}
WORKFLOW = "studio.yml"


def say(msg: str = "") -> None:
    print(msg, flush=True)


def run(cmd: list[str], cwd: Path | None = None, input: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, input=input, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}… : {(r.stderr or r.stdout).strip()[:400]}")
    return r


def ask(question: str, default: str = "o") -> bool:
    rep = input(f"{question} [{'O/n' if default == 'o' else 'o/N'}] ").strip().lower()
    return (rep or default).startswith("o")


def tools_ok() -> bool:
    ok = True
    for tool, wid in (("git", "Git.Git"), ("gh", "GitHub.cli")):
        if shutil.which(tool) is None:
            say(f"❌ {tool} n'est pas installé. Installe-le avec :  winget install --id {wid}")
            ok = False
    if not ok:
        say("   Puis FERME cette fenêtre et relance (Windows ne voit les nouveaux programmes qu'après).")
    return ok


def login() -> tuple[str, str]:
    st = run(["gh", "auth", "status"], check=False)
    if st.returncode != 0:
        say("\n🔑 Connexion à GitHub : un code va s'afficher, puis ton navigateur s'ouvre.")
        say("   Copie le code dans la page, clique sur « Continue » puis « Authorize github ».\n")
        subprocess.run(["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web",
                        "--scopes", "workflow"])          # « workflow » : permet d'envoyer le fichier du robot
        st = run(["gh", "auth", "status"], check=False)
        if st.returncode != 0:
            raise RuntimeError("Connexion à GitHub non terminée. Relance le programme.")
    elif "workflow" not in (st.stdout + st.stderr):
        say("\n🔑 GitHub doit autoriser l'envoi du robot : valide dans la page qui s'ouvre.\n")
        subprocess.run(["gh", "auth", "refresh", "--hostname", "github.com", "--scopes", "workflow"])
    run(["gh", "auth", "setup-git"], check=False)
    user = json.loads(run(["gh", "api", "user"]).stdout)
    return user["login"], str(user["id"])


def sync() -> None:
    """Recopie le code dans DEPOT (en gardant l'historique Git), sans data/ ni clés."""
    DEPOT.mkdir(exist_ok=True)
    wanted = set()
    for f in SRC.rglob("*"):
        rel = f.relative_to(SRC)
        if any(part in EXCLUS for part in rel.parts) or f.suffix == ".pyc" or not f.is_file():
            continue
        wanted.add(rel)
        dst = DEPOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    for f in sorted(DEPOT.rglob("*"), reverse=True):
        rel = f.relative_to(DEPOT)
        if rel.parts[0] == ".git":
            continue
        if f.is_file() and rel not in wanted:
            f.unlink()
        elif f.is_dir() and not any(f.iterdir()):
            f.rmdir()
    if any("settings.json" in p.name for p in DEPOT.rglob("*") if ".git" not in p.parts):
        raise RuntimeError("settings.json ne doit jamais partir sur GitHub : arrêt par sécurité")


def push(repo: str, login_: str, uid: str) -> None:
    g = lambda *a, **k: run(["git", *a], cwd=DEPOT, **k)  # noqa: E731
    if not (DEPOT / ".git").exists():
        g("init", "-b", "main")
    g("config", "user.name", login_)
    g("config", "user.email", f"{uid}+{login_}@users.noreply.github.com")   # adresse anonyme fournie par GitHub
    g("add", "-A")
    if g("status", "--porcelain").stdout.strip():
        g("commit", "-m", "Studio Médias : mise à jour")
    exists = run(["gh", "repo", "view", repo], check=False).returncode == 0
    if not exists:
        say(f"📦 Création du dépôt {repo} (public)…")
        run(["gh", "repo", "create", repo, "--public", "--description", "Studio Médias (robot d'actualité)"])
    url = f"https://github.com/{repo}.git"
    if g("remote", "get-url", "origin", check=False).returncode != 0:
        g("remote", "add", "origin", url)
    else:
        g("remote", "set-url", "origin", url)
    if exists and g("ls-remote", "--heads", "origin", "main").stdout.strip():
        g("fetch", "origin", "main")
        g("rebase", "origin/main", check=False)     # récupère les « commits de maintien » faits par le robot
    say("⬆️  Envoi du code…")
    g("push", "-u", "origin", "main")


def send_secrets(repo: str) -> None:
    sys.path.insert(0, str(SRC))
    from secrets_pour_github import collect

    items = collect()
    names = [n for n, _ in items]
    if "GEMINI_API_KEY" not in names:
        say("⚠️  Pas de clé Gemini dans le studio : ajoute-la dans Réglages puis relance, sinon rien ne sera généré.")
    if not any(n.startswith("BUFFER_KEY") or n.startswith("IG_") for n in names):
        say("ℹ️  Aucun compte de publication branché : le robot préparera les posts sans les publier.")
    for name, value in items:
        run(["gh", "secret", "set", name, "--repo", repo], input=value)
    say(f"🔐 {len(items)} secret(s) copiés dans le dépôt (chiffrés, invisibles même pour toi sur GitHub).")


def enable(repo: str) -> None:
    r = run(["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", "build_type=workflow"], check=False)
    if r.returncode != 0:
        run(["gh", "api", "-X", "PUT", f"repos/{repo}/pages", "-f", "build_type=workflow"], check=False)
    say("🌐 Page des posts activée (GitHub Pages).")
    for _ in range(10):                             # GitHub met quelques secondes à voir le workflow
        if run(["gh", "workflow", "view", WORKFLOW, "--repo", repo], check=False).returncode == 0:
            break
        time.sleep(3)
    run(["gh", "workflow", "enable", WORKFLOW, "--repo", repo], check=False)
    if run(["gh", "workflow", "run", WORKFLOW, "--repo", repo], check=False).returncode == 0:
        say("🤖 Robot activé : premier passage lancé (5 à 10 min), puis toutes les 15 min.")
    else:
        say("🤖 Robot activé. Le premier passage démarrera tout seul dans les 15 min.")


def local_off() -> None:
    sys.path.insert(0, str(SRC))
    from studio.config import load_settings, save_settings

    s = load_settings()
    pub = s.get("publish") or {}
    for c in pub.values():
        c["enabled"] = False
    save_settings({"publish": pub, "hub": {**(s.get("hub") or {}), "enabled": False}})
    say("💤 Publication auto coupée sur ce PC (c'est GitHub qui publie maintenant, pas de doublons).")


def main() -> None:
    say("=" * 62 + "\n   MISE EN LIGNE DU STUDIO SUR GITHUB (gratuit, 24h/24)\n" + "=" * 62)
    if not tools_ok():
        return
    login_, uid = login()
    say(f"✅ Connecté à GitHub : {login_}")
    memo = json.loads(MEMO.read_text(encoding="utf-8")) if MEMO.exists() else {}
    repo = memo.get("repo")
    if not repo:
        name = input("\nNom du dépôt à créer [studio-medias] : ").strip() or "studio-medias"
        repo = f"{login_}/{name}"
        say("\nLe dépôt sera PUBLIC : c'est obligatoire pour que GitHub soit gratuit et illimité.")
        say("Le code sera visible, mais JAMAIS tes clés (elles vont dans les secrets chiffrés).")
        if not ask("On continue ?"):
            return
        MEMO.parent.mkdir(parents=True, exist_ok=True)
        MEMO.write_text(json.dumps({"repo": repo}), encoding="utf-8")
    sync()
    push(repo, login_, uid)
    send_secrets(repo)
    enable(repo)
    owner, name = repo.split("/")
    if ask("\nCouper la publication auto sur ce PC pour éviter les doublons (conseillé) ?"):
        local_off()
    say("\n" + "=" * 62)
    say("🎉 C'EST EN LIGNE. Ton PC peut être éteint, tout se passe chez GitHub.")
    say(f"   Page des posts (mise à jour toutes les 15 min) : https://{owner.lower()}.github.io/{name}/")
    say(f"   Suivi du robot (coche verte = OK)              : https://github.com/{repo}/actions")
    say("   Tu reçois les notifications ntfy comme avant.")
    say("   Après une mise à jour du studio ou de tes réglages : relance METTRE_EN_LIGNE.bat")
    say("=" * 62)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nArrêté.")
    except Exception as ex:
        say(f"\n❌ Problème : {ex}\n   Rien de grave : corrige si besoin, puis relance METTRE_EN_LIGNE.bat.")
