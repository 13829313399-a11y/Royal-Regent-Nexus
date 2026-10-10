<script setup lang="ts">
import { ref } from 'vue'
import { MessageCircle, Star, ArrowUpRight, Sparkles } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import UserAvatar from '@/components/common/UserAvatar.vue'
import PresenceBadge from '@/components/directory/PresenceBadge.vue'
import type { DirectoryMember } from '@/api/directory'
import { directoryDepartmentLabel, directoryFactoryLabel } from '@/lib/directoryLabels'
import { collaborationApi } from '@/api/collaboration'
import { useAuthStore } from '@/stores/auth'
import { useMessagingStore } from '@/stores/messaging'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ member: DirectoryMember; detailed?: boolean; compact?: boolean }>()
const emit = defineEmits<{ select: [member: DirectoryMember]; chat: [member: DirectoryMember]; appreciate: [member: DirectoryMember]; contact: [] }>()
const auth = useAuthStore(), messaging = useMessagingStore(), error = ref(''), busy = ref(false)
async function toggleContact() {
  if (busy.value) return
  const who = messaging.identityKey
  busy.value = true; error.value = ''
  try { await collaborationApi.contact(props.member.id, !props.member.is_contact); if (who === messaging.identityKey) emit('contact') }
  catch (caught) { if (who === messaging.identityKey) error.value = getApiErrorMessage(caught) }
  finally { if (who === messaging.identityKey) busy.value = false }
}
</script>
<template>
  <article class="connect-member" :class="{ 'connect-member--detail': detailed, 'connect-member--compact': compact }" :data-theme="member.self_profile?.theme || 'celadon'" data-connect-member>
    <div class="connect-cover" aria-hidden="true"><span class="connect-orbit" /><span class="connect-cover-caption">NEXUS · CONNECT</span><Sparkles :size="18" /></div>
    <div class="connect-member-body">
      <div class="connect-member-heading"><button type="button" class="connect-avatar-button" :aria-label="`查看${member.display_name}的名片`" @click="emit('select', member)"><UserAvatar :src="member.avatar_url" :name="member.display_name" size="lg" /></button><PresenceBadge :state="member.presence_state" /></div>
      <button class="connect-name-button" type="button" @click="emit('select', member)"><h3>{{ member.display_name }}</h3><ArrowUpRight :size="16" /></button>
      <p class="connect-position">{{ member.position }}</p>
      <p class="connect-org">{{ member.org_name || directoryFactoryLabel(member.primary_factory_id) }} · {{ directoryDepartmentLabel(member.primary_department) }}</p>
      <p class="connect-help"><span>可以找我</span>{{ member.self_profile?.help_topics || '暂未填写职责自述' }}</p>
      <div v-if="member.self_profile?.skill_tags?.length" class="connect-tags" aria-label="本人填写的专长"><span v-for="tag in member.self_profile.skill_tags.slice(0, detailed ? 6 : 2)" :key="tag">{{ tag }}</span><span v-if="!detailed && member.self_profile.skill_tags.length > 2">+{{ member.self_profile.skill_tags.length - 2 }}</span></div>
      <p v-if="member.self_profile?.status_text || (member.self_profile?.availability && member.self_profile.availability !== 'available')" class="connect-status">{{ { available: '可联系', busy: '忙碌', leave_message: '请留言' }[member.self_profile.availability || 'available'] }} · {{ member.self_profile.status_text }}</p>
      <template v-if="detailed"><p v-if="member.self_profile?.bio" class="connect-bio">{{ member.self_profile.bio }}</p><details v-if="member.additional_assignments?.length"><summary>另有 {{ member.additional_assignments.length }} 项任职</summary><p v-for="(assignment, i) in member.additional_assignments" :key="i">{{ assignment.org_name }} · {{ directoryDepartmentLabel(assignment.department) }} · {{ assignment.position }}</p></details></template>
      <div class="connect-member-actions" v-if="messaging.ready">
        <RouterLink v-if="member.id === auth.currentUser?.id" class="connect-button connect-button--primary" to="/me">编辑我的名片</RouterLink>
        <template v-else><button v-if="member.actions?.can_message" type="button" class="connect-button connect-button--primary" @click="emit('chat', member)"><MessageCircle :size="16" />发私信</button><button type="button" class="connect-button connect-star" :class="{ selected: member.is_contact }" :aria-label="member.is_contact ? '取消常联系' : '添加常联系'" :aria-pressed="member.is_contact" :disabled="busy" @click="toggleContact"><Star :size="17" /></button><button v-if="detailed && member.actions?.can_appreciate" type="button" class="connect-button" @click="emit('appreciate', member)">感谢</button></template>
      </div><p v-if="error" class="connect-error" role="alert">{{ error }}</p>
    </div>
  </article>
</template>
