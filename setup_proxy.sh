#!/bin/bash
# setup_proxy.sh - ä»£ç†èŠ‚ç‚¹è§£æžä¸Ž sing-box å¯åŠ¨
export LC_ALL=C
set -e

# é»˜è®¤æµ‹è¯•èŠ‚ç‚¹ï¼ˆå¯é€šè¿‡çŽ¯å¢ƒå˜é‡è¦†ç›–ï¼‰
export NODE_LINK=${NODE_LINK:-''}

if [ -z "$NODE_LINK" ]; then
  echo "[INFO] æœªé…ç½®ä»£ç†ï¼Œç›´è¿žæ¨¡å¼"
  echo "IS_PROXY=false" >> $GITHUB_ENV
  exit 0
fi

if ! command -v jq &> /dev/null; then
  echo "[ERROR] jq æœªå®‰è£…ï¼Œæ­£åœ¨å®‰è£…..."
  sudo apt-get update && sudo apt-get install -y jq
fi

command -v curl &>/dev/null && COMMAND="curl -so" || command -v wget &>/dev/null && COMMAND="wget -qO" || { red "Error: neither curl nor wget found, please install one of them." >&2; exit 1; }

echo "[INFO] èŽ·å– sing-box æœ€æ–°ç‰ˆæœ¬..."
latest_version=$(curl -s "https://api.github.com/repos/SagerNet/sing-box/releases" | jq -r '[.[] | select(.prerelease==false)][0].tag_name | sub("^v"; "")')
if [ -z "$latest_version" ]; then
  echo "[ERROR] æ— æ³•èŽ·å– sing-box æœ€æ–°ç‰ˆæœ¬,å°†ä¸‹è½½v1.13.14"
  export latest_version=1.13.14
fi
echo "[INFO] æœ€æ–°ç¨³å®šç‰ˆæœ¬: v${latest_version}"

ARCH_RAW=$(uname -m)
case "${ARCH_RAW}" in
    'x86_64' | 'amd64')  ARCH='amd64' ;;
    'x86' | 'i686' | 'i386') ARCH='386' ;;
    'aarch64' | 'arm64') ARCH='arm64' ;;
    'armv7l')  ARCH='armv7' ;;
    's390x')   ARCH='s390x' ;;
    *) echo "ä¸æ”¯æŒçš„æž¶æž„: ${ARCH_RAW}"; exit 1 ;;
esac

$COMMAND sing-box-${latest_version}-linux-${ARCH}.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v${latest_version}/sing-box-${latest_version}-linux-${ARCH}.tar.gz"
tar -xzf "sing-box-${latest_version}-linux-${ARCH}.tar.gz"
mv "sing-box-${latest_version}-linux-${ARCH}/sing-box" ./
rm -f "sing-box-${latest_version}-linux-${ARCH}.tar.gz"
rm -rf "sing-box-${latest_version}-linux-${ARCH}"
chmod +x sing-box

proto=$(echo "$NODE_LINK" | cut -d':' -f1)
content="${NODE_LINK#*://}"
content="${content%%#*}"

echo "[INFO] åè®®: $proto"
# echo "[INFO] åŽŸå§‹å†…å®¹: $content"

# åˆå§‹åŒ–å˜é‡
outbound_type=""
outbound_server=""
outbound_port=""
outbound_uuid=""
outbound_flow=""
outbound_transport_type="tcp"
outbound_path="/"
outbound_host=""
outbound_security="none"
outbound_sni=""
outbound_fingerprint="chrome"
outbound_reality_pbk=""
outbound_reality_sid=""
outbound_password=""
outbound_up_mbps=100
outbound_down_mbps=100
outbound_obfs_password=""
outbound_auth=""
outbound_congestion="bbr"
outbound_udp_over_stream="true"
outbound_zerortt="false"
outbound_username=""
outbound_password2=""
outbound_version="5"
outbound_insecure="false"
outbound_alpn=""

# è¾…åŠ©å‡½æ•°ï¼šURL è§£ç 
url_decode() {
  local encoded="$1"
  printf '%b' "$(echo "$encoded" | sed 's/%/\\x/g')"
}

case "$proto" in
  vless)
    uuid_host="${content#*://}"
    uuid="${uuid_host%%@*}"
    rest="${uuid_host#*@}"
    if [[ "$rest" == *"?"* ]]; then
      host_port="${rest%%\?*}"
      query="${rest#*\?}"
    else
      host_port="$rest"
      query=""
    fi
    outbound_server="${host_port%:*}"
    outbound_port="${host_port#*:}"
    outbound_uuid="$uuid"
    outbound_type="vless"
    if [ -n "$query" ]; then
      flow=$(echo "$query" | grep -o 'flow=[^&]*' | cut -d= -f2)
      [ -n "$flow" ] && outbound_flow="$flow"
      ttype=$(echo "$query" | grep -o 'type=[^&]*' | cut -d= -f2)
      [ -n "$ttype" ] && outbound_transport_type="$ttype"
      path_raw=$(echo "$query" | grep -o 'path=[^&]*' | cut -d= -f2)
      if [ -n "$path_raw" ]; then
        path_decoded=$(url_decode "$path_raw")
        outbound_path="${path_decoded%%\?*}"
      fi
      host=$(echo "$query" | grep -o 'host=[^&]*' | cut -d= -f2)
      [ -n "$host" ] && outbound_host="$host"
      sec=$(echo "$query" | grep -o 'security=[^&]*' | cut -d= -f2)
      [ -n "$sec" ] && outbound_security="$sec"
      sni=$(echo "$query" | grep -o 'sni=[^&]*' | cut -d= -f2)
      [ -n "$sni" ] && outbound_sni="$sni"
      fp=$(echo "$query" | grep -o 'fp=[^&]*' | cut -d= -f2)
      [ -n "$fp" ] && outbound_fingerprint="$fp"
      pbk=$(echo "$query" | grep -o 'pbk=[^&]*' | cut -d= -f2)
      [ -n "$pbk" ] && outbound_reality_pbk="$pbk"
      sid=$(echo "$query" | grep -o 'sid=[^&]*' | cut -d= -f2)
      [ -n "$sid" ] && outbound_reality_sid="$sid"
      ins=$(echo "$query" | grep -o 'insecure=[^&]*' | cut -d= -f2)
      [ "$ins" = "1" ] || [ "$ins" = "true" ] && outbound_insecure="true"
      alins=$(echo "$query" | grep -o 'allowInsecure=[^&]*' | cut -d= -f2)
      [ "$alins" = "1" ] || [ "$alins" = "true" ] && outbound_insecure="true"
    fi
    [ -z "$outbound_host" ] && outbound_host="$outbound_server"
    [ -z "$outbound_sni" ] && outbound_sni="$outbound_server"
    ;;

  vmess)
    b64="${content}"
    mod=$(( ${#b64} % 4 ))
    if [ $mod -eq 2 ]; then b64="${b64}=="; elif [ $mod -eq 3 ]; then b64="${b64}="; fi
    decoded=$(echo "$b64" | base64 -d 2>/dev/null)
    if [ -z "$decoded" ]; then
      echo "[ERROR] VMess è§£ç å¤±è´¥"
      exit 1
    fi
    add=$(echo "$decoded" | jq -r '.add // ""')
    port=$(echo "$decoded" | jq -r '.port // 443')
    id=$(echo "$decoded" | jq -r '.id // ""')
    aid=$(echo "$decoded" | jq -r '.aid // 0')
    net=$(echo "$decoded" | jq -r '.net // "tcp"')
    tls=$(echo "$decoded" | jq -r '.tls // ""')
    sni=$(echo "$decoded" | jq -r '.sni // ""')
    host=$(echo "$decoded" | jq -r '.host // ""')
    path_raw=$(echo "$decoded" | jq -r '.path // "/"')
    path_decoded=$(url_decode "$path_raw")
    outbound_path="${path_decoded%%\?*}"
    fp=$(echo "$decoded" | jq -r '.fp // "chrome"')
    scy=$(echo "$decoded" | jq -r '.scy // "auto"')
    outbound_type="vmess"
    outbound_server="$add"
    outbound_port="$port"
    outbound_uuid="$id"
    outbound_transport_type="$net"
    outbound_host="${host:-$add}"
    outbound_sni="${sni:-$add}"
    outbound_fingerprint="$fp"
    outbound_security="$tls"
    outbound_flow=""
    ;;

  trojan)
    pass_rest="${content#*://}"
    password="${pass_rest%%@*}"
    rest="${pass_rest#*@}"
    if [[ "$rest" == *"?"* ]]; then
      host_port="${rest%%\?*}"
      query="${rest#*\?}"
    else
      host_port="$rest"
      query=""
    fi
    outbound_server="${host_port%:*}"
    outbound_port="${host_port#*:}"
    outbound_password="$password"
    outbound_type="trojan"
    if [ -n "$query" ]; then
      ttype=$(echo "$query" | grep -o 'type=[^&]*' | cut -d= -f2)
      [ -n "$ttype" ] && outbound_transport_type="$ttype"
      path_raw=$(echo "$query" | grep -o 'path=[^&]*' | cut -d= -f2)
      if [ -n "$path_raw" ]; then
        path_decoded=$(url_decode "$path_raw")
        outbound_path="${path_decoded%%\?*}"
      fi
      host=$(echo "$query" | grep -o 'host=[^&]*' | cut -d= -f2)
      [ -n "$host" ] && outbound_host="$host"
      sni=$(echo "$query" | grep -o 'sni=[^&]*' | cut -d= -f2)
      [ -n "$sni" ] && outbound_sni="$sni"
      fp=$(echo "$query" | grep -o 'fp=[^&]*' | cut -d= -f2)
      [ -n "$fp" ] && outbound_fingerprint="$fp"
      ins=$(echo "$query" | grep -o 'insecure=[^&]*' | cut -d= -f2)
      [ "$ins" = "1" ] || [ "$ins" = "true" ] && outbound_insecure="true"
      alins=$(echo "$query" | grep -o 'allowInsecure=[^&]*' | cut -d= -f2)
      [ "$alins" = "1" ] || [ "$alins" = "true" ] && outbound_insecure="true"
    fi
    [ -z "$outbound_host" ] && outbound_host="$outbound_server"
    [ -z "$outbound_sni" ] && outbound_sni="$outbound_server"
    ;;

  hysteria2|hy2)
    auth=""
    if [[ "$content" == *"@"* ]]; then
      auth="${content%%@*}"
      host_port="${content#*@}"
    else
      host_port="$content"
    fi
    if [[ "$host_port" == *"?"* ]]; then
      hp="${host_port%%\?*}"
      query="${host_port#*\?}"
    else
      hp="$host_port"
      query=""
    fi
    hp="${hp%/}"                    
    outbound_server="${hp%:*}"
    outbound_port="${hp#*:}"
    outbound_type="hysteria2"
    outbound_auth="$auth"
    
    if [ -n "$query" ]; then
      obfs=$(echo "$query" | grep -o 'obfs=[^&]*' | cut -d= -f2)
      [ -n "$obfs" ] && outbound_obfs_password="$obfs"
      sni=$(echo "$query" | grep -o 'sni=[^&]*' | cut -d= -f2)
      [ -n "$sni" ] && outbound_sni="$sni"
      fp=$(echo "$query" | grep -o 'fp=[^&]*' | cut -d= -f2)
      [ -n "$fp" ] && outbound_fingerprint="$fp"
      ins=$(echo "$query" | grep -o 'insecure=[^&]*' | cut -d= -f2)
      [ "$ins" = "1" ] || [ "$ins" = "true" ] && outbound_insecure="true"
      alins=$(echo "$query" | grep -o 'allowInsecure=[^&]*' | cut -d= -f2)
      [ "$alins" = "1" ] || [ "$alins" = "true" ] && outbound_insecure="true"
    fi
    [ -z "$outbound_sni" ] && outbound_sni="$outbound_server"
    ;;

  tuic)
    # åˆ†ç¦» uuid:password éƒ¨åˆ†ï¼ˆç”¨ %3A åˆ†éš”ï¼‰
    uuid_pass="${content%%@*}"
    rest="${content#*@}"
    # æ›¿æ¢ %3A ä¸º :
    uuid_pass_clean=$(echo "$uuid_pass" | sed 's/%3A/:/g')
    if [[ "$uuid_pass_clean" == *":"* ]]; then
      outbound_uuid="${uuid_pass_clean%:*}"
      outbound_password2="${uuid_pass_clean#*:}"
    else
      outbound_uuid="$uuid_pass_clean"
      outbound_password2=""
    fi
    # è§£æž host:port å’Œ query
    if [[ "$rest" == *"?"* ]]; then
      host_port="${rest%%\?*}"
      query="${rest#*\?}"
    else
      host_port="$rest"
      query=""
    fi
    outbound_server="${host_port%:*}"
    outbound_port="${host_port#*:}"
    outbound_type="tuic"
    # è§£æžå‚æ•°
    if [ -n "$query" ]; then
      sni=$(echo "$query" | grep -o 'sni=[^&]*' | cut -d= -f2)
      [ -n "$sni" ] && outbound_sni="$sni"
      fp=$(echo "$query" | grep -o 'fp=[^&]*' | cut -d= -f2)
      [ -n "$fp" ] && outbound_fingerprint="$fp"
      ins=$(echo "$query" | grep -o 'insecure=[^&]*' | cut -d= -f2)
      [ "$ins" = "1" ] || [ "$ins" = "true" ] && outbound_insecure="true"
      alins=$(echo "$query" | grep -o 'allowInsecure=[^&]*' | cut -d= -f2)
      [ "$alins" = "1" ] || [ "$alins" = "true" ] && outbound_insecure="true"
      cc=$(echo "$query" | grep -o 'congestion_control=[^&]*' | cut -d= -f2)
      [ -n "$cc" ] && outbound_congestion="$cc"
      alpn=$(echo "$query" | grep -o 'alpn=[^&]*' | cut -d= -f2)
      [ -n "$alpn" ] && outbound_alpn="$alpn"
    fi
    [ -z "$outbound_sni" ] && outbound_sni="$outbound_server"
    ;;

  anytls)
    password="${content%%@*}"
    rest="${content#*@}"
    if [[ "$rest" == *"?"* ]]; then
      host_port="${rest%%\?*}"
      query="${rest#*\?}"
    else
      host_port="$rest"
      query=""
    fi
    outbound_server="${host_port%:*}"
    outbound_port="${host_port#*:}"
    outbound_password="$password"
    outbound_type="anytls"
    if [ -n "$query" ]; then
      sni=$(echo "$query" | grep -o 'sni=[^&]*' | cut -d= -f2)
      [ -n "$sni" ] && outbound_sni="$sni"
      fp=$(echo "$query" | grep -o 'fp=[^&]*' | cut -d= -f2)
      [ -n "$fp" ] && outbound_fingerprint="$fp"
      ins=$(echo "$query" | grep -o 'insecure=[^&]*' | cut -d= -f2)
      [ "$ins" = "1" ] || [ "$ins" = "true" ] && outbound_insecure="true"
      alins=$(echo "$query" | grep -o 'allowInsecure=[^&]*' | cut -d= -f2)
      [ "$alins" = "1" ] || [ "$alins" = "true" ] && outbound_insecure="true"
    fi
    [ -z "$outbound_sni" ] && outbound_sni="$outbound_server"
    ;;

  socks5|socks)
    if [[ "$content" == *"@"* ]]; then
      user_pass="${content%%@*}"
      host_port="${content#*@}"
      decoded=$(echo "$user_pass" | base64 -d 2>/dev/null || true)
      if [ -n "$decoded" ] && [[ "$decoded" == *":"* ]]; then
        outbound_username="${decoded%:*}"
        outbound_password2="${decoded#*:}"
      else
        if [[ "$user_pass" == *":"* ]]; then
          outbound_username="${user_pass%:*}"
          outbound_password2="${user_pass#*:}"
        else
          outbound_username="$user_pass"
          outbound_password2=""
        fi
      fi
    else
      host_port="$content"
    fi
    outbound_server="${host_port%:*}"
    outbound_port="${host_port#*:}"
    outbound_type="socks"
    ;;


  *)
    echo "[ERROR] ä¸æ”¯æŒçš„åè®®: $proto"
    exit 1
    ;;
esac

if [ -z "$outbound_server" ] || [ -z "$outbound_port" ]; then
  echo "[ERROR] æ— æ³•è§£æžæœåŠ¡å™¨åœ°å€æˆ–ç«¯å£"
  exit 1
fi

# æž„å»º outbound å¯¹è±¡
jq_outbound="{\"type\":\"$outbound_type\",\"tag\":\"proxy\",\"server\":\"$outbound_server\",\"server_port\":$outbound_port"

case "$outbound_type" in
  vless)
    jq_outbound="$jq_outbound,\"uuid\":\"$outbound_uuid\""
    [ -n "$outbound_flow" ] && jq_outbound="$jq_outbound,\"flow\":\"$outbound_flow\""
    if [ "$outbound_transport_type" != "tcp" ]; then
      jq_outbound="$jq_outbound,\"transport\":{\"type\":\"$outbound_transport_type\",\"path\":\"$outbound_path\",\"headers\":{\"Host\":\"$outbound_host\"}}"
    fi
    tls_enabled="false"
    [ "$outbound_security" = "tls" ] || [ "$outbound_security" = "reality" ] && tls_enabled="true"
    tls_json="{\"enabled\":$tls_enabled,\"server_name\":\"$outbound_sni\",\"insecure\":$outbound_insecure,\"utls\":{\"enabled\":true,\"fingerprint\":\"$outbound_fingerprint\"}"
    [ "$outbound_security" = "reality" ] && tls_json="$tls_json,\"reality\":{\"enabled\":true,\"public_key\":\"$outbound_reality_pbk\",\"short_id\":\"$outbound_reality_sid\"}"
    tls_json="$tls_json}"
    jq_outbound="$jq_outbound,\"tls\":$tls_json"
    ;;
  vmess)
    jq_outbound="$jq_outbound,\"uuid\":\"$outbound_uuid\",\"security\":\"auto\""
    jq_outbound="$jq_outbound,\"transport\":{\"type\":\"$outbound_transport_type\",\"path\":\"$outbound_path\",\"headers\":{\"Host\":\"$outbound_host\"}}"
    tls_enabled="false"
    [ "$outbound_security" = "tls" ] && tls_enabled="true"
    jq_outbound="$jq_outbound,\"tls\":{\"enabled\":$tls_enabled,\"server_name\":\"$outbound_sni\",\"insecure\":$outbound_insecure,\"utls\":{\"enabled\":true,\"fingerprint\":\"$outbound_fingerprint\"}}"
    ;;
  trojan)
    jq_outbound="$jq_outbound,\"password\":\"$outbound_password\""
    jq_outbound="$jq_outbound,\"transport\":{\"type\":\"$outbound_transport_type\",\"path\":\"$outbound_path\",\"headers\":{\"Host\":\"$outbound_host\"}}"
    jq_outbound="$jq_outbound,\"tls\":{\"enabled\":true,\"server_name\":\"$outbound_sni\",\"insecure\":$outbound_insecure,\"utls\":{\"enabled\":true,\"fingerprint\":\"$outbound_fingerprint\"}}"
    ;;
  hysteria2)
    jq_outbound="$jq_outbound,\"up_mbps\":$outbound_up_mbps,\"down_mbps\":$outbound_down_mbps"
    [ -n "$outbound_obfs_password" ] && jq_outbound="$jq_outbound,\"obfs\":{\"type\":\"salamander\",\"password\":\"$outbound_obfs_password\"}"
    [ -n "$outbound_auth" ] && jq_outbound="$jq_outbound,\"password\":\"$outbound_auth\""
    jq_outbound="$jq_outbound,\"tls\":{\"enabled\":true,\"server_name\":\"$outbound_sni\",\"insecure\":$outbound_insecure}"
    ;;
  tuic)
    jq_outbound="$jq_outbound,\"uuid\":\"$outbound_uuid\""
    [ -n "$outbound_password2" ] && jq_outbound="$jq_outbound,\"password\":\"$outbound_password2\""
    jq_outbound="$jq_outbound,\"congestion_control\":\"$outbound_congestion\",\"udp_over_stream\":$outbound_udp_over_stream,\"zero_rtt_handshake\":$outbound_zerortt"
    tls_json="{\"enabled\":true,\"server_name\":\"$outbound_sni\",\"insecure\":$outbound_insecure"
    if [ -n "$outbound_alpn" ]; then
      tls_json="$tls_json,\"alpn\":[\"$outbound_alpn\"]"
    fi
    tls_json="$tls_json}"
    jq_outbound="$jq_outbound,\"tls\":$tls_json"
    ;;
  anytls)
    jq_outbound="$jq_outbound,\"password\":\"$outbound_password\""
    jq_outbound="$jq_outbound,\"tls\":{\"enabled\":true,\"server_name\":\"$outbound_sni\",\"insecure\":$outbound_insecure,\"utls\":{\"enabled\":true,\"fingerprint\":\"$outbound_fingerprint\"}}"
    ;;
  socks)
    [ -n "$outbound_username" ] && jq_outbound="$jq_outbound,\"username\":\"$outbound_username\""
    [ -n "$outbound_password2" ] && jq_outbound="$jq_outbound,\"password\":\"$outbound_password2\""
    jq_outbound="$jq_outbound,\"version\":\"$outbound_version\""
    ;;
esac
jq_outbound="$jq_outbound}"

# ç”Ÿæˆé…ç½®ï¼ˆæ—  udp å­—æ®µï¼‰
cat << EOF > sing-box-config.json
{
  "log": {"level": "warn"},
  "inbounds": [
    {"type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 1080},
    {"type": "http", "tag": "http-in", "listen": "127.0.0.1", "listen_port": 1081}
  ],
  "outbounds": [$jq_outbound]
}
EOF

# echo "[DEBUG] ç”Ÿæˆçš„ sing-box é…ç½®:"
# cat sing-box-config.json

if ! jq empty sing-box-config.json 2>/dev/null; then
  echo "[ERROR] ç”Ÿæˆçš„ sing-box é…ç½®æ— æ•ˆ"
  # cat sing-box-config.json
  exit 1
fi

echo "[INFO] âœ… sing-box é…ç½®å·²ç”Ÿæˆ"

# æ¸…ç†æ—§è¿›ç¨‹
echo "[INFO] æ¸…ç†æ—§è¿›ç¨‹..."
pkill -f sing-box 2>/dev/null || true
fuser -k 1080/tcp 2>/dev/null || true
sleep 2

./sing-box run -c sing-box-config.json > sing-box.log 2>&1 &
sleep 5

if ! pgrep -f sing-box > /dev/null; then
  echo "[ERROR] sing-box è¿›ç¨‹å¯åŠ¨å¤±è´¥ï¼ŒæŸ¥çœ‹æ—¥å¿—:"
  cat sing-box.log
  exit 1
fi

echo "[INFO] æµ‹è¯•ä»£ç†è¿žæŽ¥..."
for i in {1..3}; do
  if curl -x socks5://127.0.0.1:1080 -s --max-time 15 https://api.ipify.org > /dev/null 2>&1; then
    echo "[INFO] âœ… ä»£ç†è¿žæŽ¥æˆåŠŸ"
    echo "IS_PROXY=true" >> $GITHUB_ENV
    echo "PROXY_SERVER=socks5://127.0.0.1:1080" >> $GITHUB_ENV

    export http_proxy=http://127.0.0.1:1081
    export https_proxy=http://127.0.0.1:1081
    export ALL_PROXY=socks5://127.0.0.1:1080
    export no_proxy=localhost,127.0.0.1,::1

    sudo tee /etc/profile.d/proxy.sh > /dev/null << 'PEOF'
export http_proxy=http://127.0.0.1:1081
export https_proxy=http://127.0.0.1:1081
export ALL_PROXY=socks5://127.0.0.1:1080
export no_proxy=localhost,127.0.0.1,::1
PEOF
    sudo chmod 644 /etc/profile.d/proxy.sh

    sudo tee /etc/apt/apt.conf.d/95proxy > /dev/null << 'AEOF'
Acquire::http::Proxy "http://127.0.0.1:1081";
Acquire::https::Proxy "http://127.0.0.1:1081";
AEOF

    git config --global http.proxy http://127.0.0.1:1081
    git config --global https.proxy http://127.0.0.1:1081

    echo "[INFO] 全局代理已配置:"
    echo "  - 环境变量: http_proxy / https_proxy / ALL_PROXY"
    echo "  - 新终端自动加载: /etc/profile.d/proxy.sh"
    echo "  - apt 代理: /etc/apt/apt.conf.d/95proxy"
    echo "  - git 代理: ~/.gitconfig"
    echo ""
    echo "[INFO] 当前终端请执行: source /etc/profile.d/proxy.sh"
    exit 0
  fi
  echo "[WARN] å°è¯• $i/3..."
  sleep 3
done

echo "[ERROR] âŒ ä»£ç†è¿žæŽ¥å¤±è´¥"
echo "---- sing-box æ—¥å¿— ----"
cat sing-box.log
exit 1