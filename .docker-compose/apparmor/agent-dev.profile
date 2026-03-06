#include <tunables/global>

profile agent-dev flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  file,
  capability,

  network inet stream,
  network inet6 stream,
  network inet dgram,
  network inet6 dgram,

  deny mount,
  deny pivot_root,
  deny /sys/** wklx,
  deny /proc/sys/** wklx,
  deny /proc/*/mem rw,
  deny /proc/kcore rw,

  /usr/bin/** ix,
  /bin/** ix,
  /usr/sbin/** ix,
  /sbin/** ix,
  /usr/local/bin/** ix,

  /lib/** mr,
  /usr/lib/** mr,
  /lib64/** mr,
  /usr/lib64/** mr,

  /home/** rwk,
  /home/**/.config/** rwk,
  /home/**/.cache/** rwk,
  /home/**/.local/** rwk,
  /tmp/** rwk,
  /var/tmp/** rwk,
  /dev/shm/** rwk,

  deny /root/** rwx,
  deny /etc/shadow rw,
  deny /etc/gshadow rw,
  deny /etc/sudoers rw,
  deny /etc/sudoers.d/** rw,
}
