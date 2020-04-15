import React from "react";
import {Breadcrumb} from "semantic-ui-react";
import { Link } from "found";


class Breadcrumbs extends React.Component {
    constructor(props) {
        super(props);
        if (this.props.paths) {
            this.crumbs = this.props.paths.map(({name, path}, index, {length}) => 
                <React.Fragment key={name}>
                    <Breadcrumb.Divider icon='right chevron'/>
                    <Breadcrumb.Section>
                    {
                        index === length ?
                            <Link to={path} match={this.props.match} router={this.props.router}>
                                {name}
                            </Link>
                        : name
                    }
                    </Breadcrumb.Section>
                </React.Fragment>
            )
        } else {
            this.crumbs = []
        }

        this.crumbs.unshift(
            <React.Fragment key={'home'}>
                <Breadcrumb.Section>
                    <Link to={'/bilby'} match={this.props.match} router={this.props.router}>
                        Bilby Home
                    </Link>
                </Breadcrumb.Section>
            </React.Fragment>
        )
    }


    render() {
        return (
            <Breadcrumb>
                {this.crumbs}
            </Breadcrumb>
        )
    }
}

export default Breadcrumbs;