import json, os

nb_path = "d:/Applications/AnimeRecap/notebooks/anime-renderizador-kaggle-pt-1.ipynb"

with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

for cell in nb["cells"]:
    if cell.get("cell_type") == "code":
        source = cell["source"]
        source_str = "".join(source)
        if "colorchannelmixer" in source_str:
            print("Célula encontrada!")
            # Procura a linha "        if ov[\"type\"] in [\"image\", \"watermark\"]:\n"
            # e a linha "    overlays = config.get(\"overlays\", [])\n"
            idx_start = -1
            for idx, line in enumerate(source):
                if "overlays = config.get(" in line:
                    idx_start = idx
                    break
            
            print(f"Index start: {idx_start}")
            
            # Vamos achar o final do bloco overlay (antes de `# 6. Blur Band`)
            idx_end = -1
            for idx in range(idx_start, len(source)):
                if "# 6. Blur Band" in source[idx]:
                    idx_end = idx
                    break
            print(f"Index end: {idx_end}")

            if idx_start != -1 and idx_end != -1:
                replacement_lines = [
                    "    # 5. Overlays (Image/Text)\n",
                    "    overlays = config.get(\"overlays\", [])\n",
                    "    for i, ov in enumerate(overlays):\n",
                    "        tin = ov.get(\"timeIn\", 0) - start_time\n",
                    "        tout = ov.get(\"timeOut\", 0) - start_time\n",
                    "        if ov.get(\"timeOut\", 0) == 0: tout = 999999\n",
                    "        if tout <= 0: continue\n",
                    "\n",
                    "        if ov[\"type\"] in [\"image\", \"watermark\"]:\n",
                    "            header, encoded = ov[\"content\"].split(\",\", 1)\n",
                    "            ext = header.split(\";\")[0].split(\"/\")[1]\n",
                    "            filename = f\"/kaggle/working/temp_overlay_{i}.{ext}\"\n",
                    "            with open(filename, \"wb\") as f:\n",
                    "                f.write(base64.b64decode(encoded))\n",
                    "            overlay_inputs.append(filename)\n",
                    "            input_idx = len(overlay_inputs) + 1\n",
                    "            ox = int((ov[\"x\"] / 100.0) * out_w)\n",
                    "            oy = int((ov[\"y\"] / 100.0) * out_h)\n",
                    "            ow = int((ov[\"width\"] / 100.0) * out_w)\n",
                    "            oh = int((ov[\"height\"] / 100.0) * out_h)\n",
                    "            opacity = ov.get(\"opacity\", 1.0)\n",
                    "            filters.append(f\"[{input_idx}:v]scale={ow}:{oh}[ov_scaled_{i}]\")\n",
                    "            alpha_filter = f\",colorchannelmixer=aa={opacity}\" if opacity < 1.0 else \"\"\n",
                    "            filters.append(f\"[ov_scaled_{i}]format=rgba{alpha_filter}[ov_alpha_{i}]\")\n",
                    "            if tin < 0: tin = 0\n",
                    "            time_filter = f\":enable='between(t,{tin},{tout})'\"\n",
                    "            filters.append(f\"{last_stream}[ov_alpha_{i}]overlay=x={ox}:y={oy}{time_filter}[with_ov_{i}]\")\n",
                    "            last_stream = f\"[with_ov_{i}]\"\n",
                    "        elif ov[\"type\"] == \"text\":\n",
                    "            ox = int((ov[\"x\"] / 100.0) * out_w)\n",
                    "            oy = int((ov[\"y\"] / 100.0) * out_h)\n",
                    "            txt = ov[\"content\"].replace(\"'\", \"\\\\'\").replace(\":\", \"\\\\\\\\:\")\n",
                    "            fsize = int((ov.get(\"fontSize\", 32) * (out_h / 1080)))\n",
                    "            fcolor = ov.get(\"fontColor\", \"#ffffff\")\n",
                    "            \n",
                    "            ffamily = ov.get(\"fontFamily\", \"Montserrat\")\n",
                    "            ffamily_clean = ffamily.replace(\" \", \"\")  # Clean up spaces for filename search (e.g. Titan One -> TitanOne)\n",
                    "            fweight = ov.get(\"fontWeight\", \"normal\")\n",
                    "            fstyle = ov.get(\"fontStyle\", \"normal\")\n",
                    "            \n",
                    "            suffix = \"-Regular\"\n",
                    "            if fweight in [\"bold\", \"900\"]: suffix = \"-Bold\"\n",
                    "            if fweight == \"900\" and ffamily == \"Montserrat\": suffix = \"-Black\"\n",
                    "            if fstyle == \"italic\": suffix = \"-Italic\"\n",
                    "            fontfile = f\"/usr/share/fonts/truetype/custom/{ffamily_clean}{suffix}.ttf\"\n",
                    "            if not os.path.exists(fontfile):\n",
                    "                fontfile = f\"/usr/share/fonts/truetype/custom/{ffamily_clean}-Regular.ttf\"\n",
                    "            if os.path.exists(fontfile):\n",
                    "                font_opt = f\"fontfile='{fontfile}'\"\n",
                    "                print(f\"  Fonte overlay: {fontfile}\")\n",
                    "            else:\n",
                    "                font_opt = f\"font='{ffamily}'\"\n",
                    "                print(f\"  ⚠️ Fonte {ffamily_clean}{suffix}.ttf nao encontrada, usando fontconfig: {ffamily}\")\n",
                    "            \n",
                    "            bg_color = ov.get(\"bgColor\", \"\")\n",
                    "            bg_op = ov.get(\"bgOpacity\", 0.5)\n",
                    "            box_filter = f\":box=1:boxcolor={bg_color.replace('#','')}@{bg_op}:boxborderw={int(fsize*0.2)}\" if bg_color else \"\"\n",
                    "            \n",
                    "            shadow_color = ov.get(\"shadowColor\", \"\")\n",
                    "            shadow_filter = f\":shadowcolor={shadow_color.replace('#','')}:shadowx={ov.get('shadowX', 2)}:shadowy={ov.get('shadowY', 2)}\" if shadow_color else \"\"\n",
                    "            \n",
                    "            if tin < 0: tin = 0\n",
                    "            time_filter = f\":enable='between(t,{tin},{tout})'\"\n",
                    "            \n",
                    "            opacity = ov.get(\"opacity\", 1.0)\n",
                    "            alpha_opt = f\":alpha={opacity}\" if opacity < 1.0 else \"\"\n",
                    "            \n",
                    "            filters.append(f\"{last_stream}drawtext={font_opt}:text=\\'{txt}\\':x={ox}:y={oy}:fontsize={fsize}:fontcolor={fcolor}{box_filter}{shadow_filter}{time_filter}{alpha_opt}[with_txt_{i}]\")\n",
                    "            last_stream = f\"[with_txt_{i}]\"\n",
                    "\n"
                ]

                # Ajustar idx_start para incluir a linha de comentário "# 5. Overlays (Image/Text)" se existir
                if idx_start > 0 and "# 5. Overlays" in source[idx_start - 1]:
                    idx_start -= 1

                source[idx_start:idx_end] = replacement_lines
                cell["source"] = source
                print("Substituição precisa efetuada com sucesso!")

with open(nb_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Notebook base atualizado e salvo!")
