import { Badge } from 'react-bootstrap';
import { getBadgeType } from './getVariants';

const JobBadges = ({ labels }) => (
    <>
        {labels.map(({ name }) => (
            <Badge key={name} variant={getBadgeType(name)} className="mr-1">
                {name}
            </Badge>
        ))}
    </>
);

export default JobBadges;
