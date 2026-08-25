def process_messages(e):
    def filter_function(e):
        return bool(e)

    def parse_msg(e):
        t = {
            "params": [],
            "raw": e,
            "tags": {}
        }
        n = 0
        r = 0

        if ord(e[0]) == 64:
            r = e.find(" ")
            if r == -1:
                return None
            i = e[1:r].split(";")
            for a in i:
                s = a.find("=")
                if s != -1:
                    u = a[:s]
                    c = a[s + 1:]
                else:
                    u = a
                    c = "true"
                t["tags"][u] = c
            n = r + 1

        while n < len(e) and ord(e[n]) == 32:
            n += 1

        if ord(e[n]) == 58:
            r = e.find(" ", n)
            if r == -1:
                return None
            t["prefix"] = e[n + 1:r]
            n = r + 1

        r = e.find(" ", n)
        if r == -1:
            if len(e) > n:
                t["command"] = e[n:]
                return t
            return None

        t["command"] = e[n:r]
        n = r + 1

        while n < len(e):
            r = e.find(" ", n)
            if ord(e[n]) == 58:
                t["params"].append(e[n + 1:])
                break
            if r == -1:
                t["params"].append(e[n:])
                break
            else:
                t["params"].append(e[n:r])
                n = r + 1

        return t





    lines = e.split("\r\n")
    non_empty_lines = filter(filter_function, lines)

    for line in non_empty_lines:
        n = parse_msg(line)
        print(n)


# 调用 process_messages 函数，并传入需要处理的字符串作为参数
input_string = '@badge-info=;badges=glitchcon2020/1;client-nonce=b9af147403bd4c2cf76c32d3c940f7f3;color=#FF4500;display-name=熊哥哥的砲击手;emotes=;first-msg=0;flags=;id=96e0d9aa-9f85-47bb-b8cc-0724b7621af2;mod=0;returning-chatter=0;room-id=920125847;subscriber=0;tmi-sent-ts=1692874641583;turbo=0;user-id=28807466;user-type= :sean85232788!sean85232788@sean85232788.tmi.twitch.tv PRIVMSG #lck_carry :?'
process_messages(input_string)
