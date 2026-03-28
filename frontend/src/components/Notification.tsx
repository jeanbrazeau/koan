import { useEffect, useState } from 'react'
import { useStore, NotificationEntry } from '../store/index'

function NotificationItem({ entry }: { entry: NotificationEntry }) {
  const dismissNotification = useStore(s => s.dismissNotification)
  const [fading, setFading] = useState(false)

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFading(true), 4700)
    const removeTimer = setTimeout(() => dismissNotification(entry.id), 5000)
    return () => {
      clearTimeout(fadeTimer)
      clearTimeout(removeTimer)
    }
  }, [entry.id, dismissNotification])

  return (
    <div className={`notification ${entry.severity}${fading ? ' fade-out' : ''}`}>
      {entry.message}
    </div>
  )
}

export function Notification() {
  const notifications = useStore(s => s.notifications)

  return (
    <div id="notifications">
      {notifications.map(n => (
        <NotificationItem key={n.id} entry={n} />
      ))}
    </div>
  )
}
