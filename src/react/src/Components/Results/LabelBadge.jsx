import { HiOutlineX } from 'react-icons/hi';
import { Badge } from 'react-bootstrap';
import { getBadgeType } from '../getVariants';

const LabelBadge = ({ name, dismissable, onDismiss }) => (
    <h5 className="d-inline ml-1">
        <Badge variant={getBadgeType(name)} key={name} pill>
            {name}
            {dismissable && (
                <a data-testid="dismissable-link" role="button" className="text-light" onClick={onDismiss}>
                    <HiOutlineX className="ml-3" />
                </a>
            )}
        </Badge>
    </h5>
);

export default LabelBadge;
